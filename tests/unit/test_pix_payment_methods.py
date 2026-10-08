"""Offline coverage for BCB monthly Pix payment-method ingestion."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from meli_intelligence.metadata.pix_series import PIX_SERIES
from meli_intelligence.metadata.kpi_dictionary import kpi_dictionary_frame
from meli_intelligence.pipelines import macro_bcb_pix
from meli_intelligence.pipelines.macro_bcb_pix import build_bcb_pix_silver
from meli_intelligence.query.macro import query_macro_indicators
from meli_intelligence.sources.bcb.payment_methods_client import (
    PAYMENT_METHODS_ENDPOINT,
    PaymentMethodsClient,
    PaymentMethodsFetch,
    PaymentMethodsPage,
)
from meli_intelligence.storage.macro import merge_macro_indicators
from meli_intelligence.storage.payment_methods_bronze import (
    save_payment_methods_bronze,
)
from meli_intelligence.transformations.bcb_payment_methods import (
    normalize_payment_methods_records,
)


def _raw_row(month: str, count: str = "7021997.69", value: str = "3170990.34") -> dict:
    return {"AnoMes": month, "quantidadePix": count, "valorPix": value}


def _fetch(records: list[dict], requested: str = "202301") -> PaymentMethodsFetch:
    raw = json.dumps({"value": records}, separators=(",", ":")).encode()
    page = PaymentMethodsPage(
        source_url=f"{PAYMENT_METHODS_ENDPOINT}?@AnoMes=%27{requested}%27",
        retrieved_at="2026-10-05T12:00:00+00:00",
        raw_payload=raw,
        records=records,
    )
    return PaymentMethodsFetch(requested_start_month=requested, pages=(page,))


class _StubClient:
    def __init__(self, records: list[dict]) -> None:
        self.fetch = _fetch(records)
        self.requested = []

    def fetch_monthly_payment_methods(self, start_month: str) -> PaymentMethodsFetch:
        self.requested.append(start_month)
        return self.fetch


def test_pix_registry_has_only_two_explicit_scaled_metrics() -> None:
    assert len(PIX_SERIES) == 2
    count, value = PIX_SERIES
    assert (count.metric_id, count.source_field, count.source_series_id) == (
        "pix_transactions_count_monthly", "quantidadePix",
        "bcb_mpv:monthly:quantidadePix",
    )
    assert (count.source_unit, count.silver_unit, count.scale_factor) == (
        "thousand_transactions", "transactions", 1_000
    )
    assert (value.metric_id, value.source_field, value.source_series_id) == (
        "pix_transactions_value_monthly", "valorPix",
        "bcb_mpv:monthly:valorPix",
    )
    assert (value.source_unit, value.silver_unit, value.scale_factor) == (
        "million_brl", "brl", 1_000_000
    )


def test_client_odata_contract_nextlink_and_source_urls() -> None:
    requests = []
    page_two_url = "https://olinda.bcb.gov.br/page-two"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["User-Agent"]
        if len(requests) == 1:
            assert request.url.path == "/olinda/servico/MPV_DadosAbertos/versao/v1/odata/MeiosdePagamentosMensalDA(AnoMes=@AnoMes)"
            assert request.url.params["@AnoMes"] == "'202301'"
            assert request.url.params["$format"] == "json"
            assert request.url.params["$select"] == "AnoMes,quantidadePix,valorPix"
            return httpx.Response(
                200,
                json={"value": [_raw_row("202301")], "@odata.nextLink": page_two_url},
                request=request,
            )
        return httpx.Response(200, json={"value": [_raw_row("202302")]}, request=request)

    transport = httpx.MockTransport(handler)
    with PaymentMethodsClient(transport=transport, timeout=4) as client:
        fetched = client.fetch_monthly_payment_methods("202301")
    assert fetched.requested_start_month == "202301"
    assert [record["AnoMes"] for record in fetched.records] == ["202301", "202302"]
    assert len(fetched.pages) == 2
    assert fetched.pages[0].source_url.startswith(PAYMENT_METHODS_ENDPOINT)
    assert fetched.pages[1].source_url == page_two_url
    assert all(page.raw_payload for page in fetched.pages)


@pytest.mark.parametrize(
    ("status", "body", "match"),
    [
        (500, b"error", "500"),
        (200, b"<html>bad</html>", "not valid JSON"),
        (200, b'{"d":[]}', "value list"),
        (200, b'{"value":[{"AnoMes":"202301"}]}', "missing required fields"),
    ],
)
def test_client_rejects_invalid_responses(status: int, body: bytes, match: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, request=request)

    with PaymentMethodsClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises((httpx.HTTPStatusError, ValueError), match=match):
            client.fetch_monthly_payment_methods("202301")


def test_client_rejects_month_before_requested_lower_bound() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [_raw_row("202212")]}, request=request)

    with PaymentMethodsClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="precedes requested lower bound"):
            client.fetch_monthly_payment_methods("202301")


@pytest.mark.parametrize(
    ("month", "expected"),
    [("202302", date(2023, 2, 28)), ("202402", date(2024, 2, 29))],
)
def test_transformer_scales_source_units_and_uses_month_end(
    month: str, expected: date
) -> None:
    frame = normalize_payment_methods_records(
        [_raw_row(month)],
        source_url="https://official.example/source",
        retrieved_at="2026-10-05T12:00:00+00:00",
    )
    assert list(frame["metric_id"]) == [
        "pix_transactions_count_monthly", "pix_transactions_value_monthly"
    ]
    assert list(frame["reference_date"]) == [expected, expected]
    assert frame.iloc[0]["value"] == 7_021_997_690
    assert frame.iloc[1]["value"] == 3_170_990_340_000
    assert list(frame["source_url"]) == ["https://official.example/source"] * 2


def test_real_contract_fixtures_scale_without_lossy_intermediate_math() -> None:
    frame = normalize_payment_methods_records(
        [_raw_row("202601", "7021997.69", "3170990.34"),
         _raw_row("202510", "1", "3315978.76")],
        source_url="https://official.example/source",
        retrieved_at="2026-10-05T12:00:00+00:00",
    )
    january_count = frame.loc[
        (frame.metric_id == "pix_transactions_count_monthly")
        & (frame.reference_date == date(2026, 1, 31)), "value"
    ].iloc[0]
    october_value = frame.loc[
        (frame.metric_id == "pix_transactions_value_monthly")
        & (frame.reference_date == date(2025, 10, 31)), "value"
    ].iloc[0]
    assert january_count == 7_021_997_690
    assert october_value == 3_315_978_760_000


@pytest.mark.parametrize(
    "records",
    [
        [],
        [_raw_row("202313")],
        [_raw_row("202301", "-1", "1")],
        [_raw_row("202301", "NaN", "1")],
        [_raw_row("202301", "Infinity", "1")],
        [_raw_row("202301", "0.0001", "1")],
        [_raw_row("202301"), _raw_row("202301")],
    ],
)
def test_transformer_rejects_invalid_or_ambiguous_source_rows(records: list[dict]) -> None:
    with pytest.raises(ValueError):
        normalize_payment_methods_records(
            records, source_url="url", retrieved_at="2026-10-05T12:00:00+00:00"
        )


def test_bronze_preserves_each_raw_page_and_refuses_overwrite(tmp_path: Path) -> None:
    fetch = _fetch([_raw_row("202301")])
    paths = save_payment_methods_bronze(fetch, bronze_dir=tmp_path)
    raw_path, metadata_path = paths[0]
    assert raw_path.read_bytes() == fetch.pages[0].raw_payload
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["requested_start_month"] == "202301"
    assert metadata["source_url"] == fetch.pages[0].source_url
    assert metadata["payload_sha256"] == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert metadata["page_index"] == 0
    with pytest.raises(FileExistsError):
        save_payment_methods_bronze(fetch, bronze_dir=tmp_path)


def test_pipeline_fetches_once_filters_future_months_and_queries(
    tmp_path: Path,
) -> None:
    records = [_raw_row(f"2023{month:02d}") for month in range(1, 13)]
    records.extend([_raw_row("202401"), _raw_row("202601")])
    client = _StubClient(records)
    output = tmp_path / "silver" / "macro_indicators.parquet"
    silver, bronze, silver_path, metadata_path = build_bcb_pix_silver(
        date(2023, 1, 1), date(2023, 12, 31), client=client,
        bronze_dir=tmp_path / "bronze", output_path=output,
    )
    assert client.requested == ["202301"]
    assert len(bronze) == 1 and metadata_path.exists()
    assert len(silver) == 24
    assert set(silver.metric_id) == {series.metric_id for series in PIX_SERIES}
    assert max(silver.reference_date) == date(2023, 12, 31)
    count = query_macro_indicators(
        parquet_path=silver_path,
        metric_id="pix_transactions_count_monthly",
        start_date=date(2023, 1, 1), end_date=date(2023, 12, 31),
    )
    value = query_macro_indicators(
        parquet_path=silver_path,
        metric_id="pix_transactions_value_monthly",
        start_date=date(2023, 1, 1), end_date=date(2023, 12, 31),
    )
    assert len(count) == len(value) == 12
    assert count.iloc[0]["reference_date"].date() == date(2023, 1, 31)
    assert count.iloc[-1]["reference_date"].date() == date(2023, 12, 31)


@pytest.mark.parametrize(
    "records",
    [[], [_raw_row("202401")]],
)
def test_pipeline_empty_requested_range_does_not_persist_silver(
    tmp_path: Path, records: list[dict]
) -> None:
    output = tmp_path / "silver.parquet"
    with pytest.raises(ValueError, match="No Pix observations"):
        build_bcb_pix_silver(
            date(2023, 1, 1), date(2023, 12, 31), client=_StubClient(records),
            bronze_dir=tmp_path / "bronze", output_path=output,
        )
    assert not output.exists()


def test_pipeline_rejects_client_missing_metric_identity_before_silver_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = macro_bcb_pix.normalize_payment_methods_records

    def one_metric(*args, **kwargs):
        frame = original(*args, **kwargs)
        return frame.loc[frame.metric_id == "pix_transactions_count_monthly"].copy()

    monkeypatch.setattr(macro_bcb_pix, "normalize_payment_methods_records", one_metric)
    output = tmp_path / "silver.parquet"
    with pytest.raises(ValueError, match="missing required Pix metrics"):
        build_bcb_pix_silver(
            date(2023, 1, 1), date(2023, 12, 31),
            client=_StubClient([_raw_row("202301")]),
            bronze_dir=tmp_path / "bronze", output_path=output,
        )
    assert not output.exists()


def test_pipeline_fixed_scope_drops_future_registry_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = macro_bcb_pix.normalize_payment_methods_records

    def with_future_metric(*args, **kwargs):
        frame = original(*args, **kwargs)
        future = frame.iloc[[0]].copy()
        future["metric_id"] = "future_pix_metric"
        future["source_series_id"] = "bcb_mpv:future"
        future["unit"] = "future_unit"
        return pd.concat([frame, future], ignore_index=True)

    monkeypatch.setattr(macro_bcb_pix, "normalize_payment_methods_records", with_future_metric)
    silver, *_ = build_bcb_pix_silver(
        date(2023, 1, 1), date(2023, 12, 31),
        client=_StubClient([_raw_row("202301")]),
        bronze_dir=tmp_path / "bronze", output_path=tmp_path / "silver.parquet",
    )
    assert set(silver.metric_id) == {
        "pix_transactions_count_monthly", "pix_transactions_value_monthly"
    }


def test_macro_merge_keeps_identical_lineage_and_rejects_revision() -> None:
    existing = normalize_payment_methods_records(
        [_raw_row("202301")], source_url="old", retrieved_at="old-time"
    )
    replay = existing.copy()
    replay["source_url"] = "new"
    merged = merge_macro_indicators(existing, replay)
    assert len(merged) == 2
    assert set(merged.source_url) == {"old"}
    changed = replay.copy()
    changed.loc[changed.metric_id == "pix_transactions_value_monthly", "value"] += 1
    with pytest.raises(ValueError, match="Incoming macro values conflict"):
        merge_macro_indicators(existing, changed)


def test_kpi_dictionary_count_and_pix_definitions() -> None:
    dictionary = kpi_dictionary_frame()
    assert len(dictionary) == 39
    assert dictionary.metric_id.is_unique
    pix = dictionary.set_index("metric_id")
    assert pix.loc["pix_transactions_count_monthly", "unit"] == "transactions"
    assert pix.loc["pix_transactions_value_monthly", "unit"] == "brl"
    assert "1000" in pix.loc["pix_transactions_count_monthly", "formula"]
    assert "1000000" in pix.loc["pix_transactions_value_monthly", "formula"]
