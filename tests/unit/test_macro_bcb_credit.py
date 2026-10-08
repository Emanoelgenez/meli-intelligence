"""Offline tests for monthly BCB household credit and delinquency ingestion."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.metadata import bcb_series
from meli_intelligence.metadata.bcb_series import BCBSeries, get_bcb_series
from meli_intelligence.metadata.kpi_dictionary import kpi_dictionary_frame
from meli_intelligence.pipelines.macro_bcb_credit import (
    CREDIT_SERIES_CODES,
    build_bcb_credit_silver,
)
from meli_intelligence.query.macro import query_macro_indicators
from meli_intelligence.sources.bcb.sgs_client import BCBFetch
from meli_intelligence.storage.macro import (
    merge_macro_indicators,
    read_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.transformations.bcb_sgs import normalize_sgs_payload


def _records(series_code: int) -> list[dict[str, str]]:
    return [
        {
            "data": f"01/{month:02d}/2023",
            "valor": (
                "1922367" if series_code == 20570 and month == 12
                else str(1_800_000 + month * 100) if series_code == 20570
                else str(4.0 + month / 10)
            ),
        }
        for month in range(1, 13)
    ]


def _fetch(
    series_code: int,
    start_date: date,
    end_date: date,
    *,
    empty: bool = False,
) -> BCBFetch:
    records = [] if empty else _records(series_code)
    raw_payload = json.dumps(records).encode("utf-8")
    return BCBFetch(
        series_code=series_code,
        requested_start_date=start_date,
        requested_end_date=end_date,
        source_url=(
            "https://api.bcb.gov.br/dados/serie/"
            f"bcdata.sgs.{series_code}/dados?formato=json"
        ),
        retrieved_at="2026-10-05T00:00:00+00:00",
        raw_payload=raw_payload,
        records=records,
    )


class _CreditClient:
    def __init__(self, empty_codes: tuple[int, ...] = ()) -> None:
        self.empty_codes = set(empty_codes)
        self.requested: list[int] = []

    def fetch_series(self, series_code: int, start_date: date, end_date: date):
        self.requested.append(series_code)
        return [
            _fetch(
                series_code, start_date, end_date,
                empty=series_code in self.empty_codes,
            )
        ]

    def close(self) -> None:
        pass


def _preexisting_macro_frame() -> pd.DataFrame:
    metrics = [
        ("selic_target_annual", "bcb_sgs:432", 13.75, "percent_per_year", "daily", "Banco Central do Brasil - SGS", date(2023, 1, 2)),
        ("selic_effective_annual_252", "bcb_sgs:1178", 13.65, "percent_per_year", "daily", "Banco Central do Brasil - SGS", date(2023, 1, 2)),
        ("ipca_monthly_change", "ibge_sidra:1737:63", 0.62, "percent", "monthly", "IBGE - SIDRA", date(2023, 1, 31)),
        ("ipca_12m_change", "ibge_sidra:1737:2265", 5.77, "percent", "monthly", "IBGE - SIDRA", date(2023, 1, 31)),
        ("usd_brl_sell_rate", "bcb_sgs:1", 5.2, "brl_per_usd", "daily", "Banco Central do Brasil - SGS", date(2023, 1, 2)),
    ]
    return pd.DataFrame([
        {
            "metric_id": metric_id,
            "source_series_id": source_series_id,
            "reference_date": reference_date,
            "value": value,
            "unit": unit,
            "frequency": frequency,
            "source": source,
            "source_url": "https://source.example/existing",
            "retrieved_at": "2023-02-01T00:00:00+00:00",
            "ingestion_version": "1",
        }
        for metric_id, source_series_id, value, unit, frequency, source, reference_date in metrics
    ])


def test_credit_pipeline_fetches_only_required_series_and_shares_silver(
    tmp_path: Path,
) -> None:
    assert CREDIT_SERIES_CODES == (20570, 21112)
    output = tmp_path / "macro_indicators.parquet"
    write_macro_indicators(_preexisting_macro_frame(), output_path=output)
    client = _CreditClient()
    silver, bronze, silver_path, metadata_path = build_bcb_credit_silver(
        date(2023, 1, 1), date(2023, 12, 31),
        client=client, bronze_dir=tmp_path / "bronze", output_path=output,
    )
    assert client.requested == [20570, 21112]
    assert len(bronze) == 2
    assert all(data.exists() and metadata.exists() for data, metadata in bronze)
    bronze_metadata = [json.loads(metadata.read_text(encoding="utf-8")) for _, metadata in bronze]
    assert [(row["series_code"], row["metric_id"]) for row in bronze_metadata] == [
        (20570, "household_free_credit_balance"),
        (21112, "household_free_credit_npl_90d_rate"),
    ]
    assert all(row["payload_sha256"] for row in bronze_metadata)
    assert silver_path.exists() and metadata_path.exists()

    expected_metrics = {
        "selic_target_annual", "selic_effective_annual_252",
        "ipca_monthly_change", "ipca_12m_change", "usd_brl_sell_rate",
        "household_free_credit_balance", "household_free_credit_npl_90d_rate",
    }
    assert set(silver["metric_id"]) == expected_metrics
    assert not silver.duplicated(["metric_id", "reference_date"]).any()
    restored = read_macro_indicators(silver_path)
    assert "series_code" not in restored.columns
    assert {"bcb_sgs:20570", "bcb_sgs:21112"}.issubset(set(restored["source_series_id"]))

    for metric_id in (
        "household_free_credit_balance",
        "household_free_credit_npl_90d_rate",
    ):
        queried = query_macro_indicators(
            parquet_path=silver_path,
            metric_id=metric_id,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
        )
        assert len(queried) == 12
        assert queried.iloc[0]["reference_date"].date() == date(2023, 1, 31)
        assert queried.iloc[-1]["reference_date"].date() == date(2023, 12, 31)


@pytest.mark.parametrize("empty_codes", [(20570,), (21112,), (20570, 21112)])
def test_credit_pipeline_requires_both_nonempty_series_and_fixed_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    empty_codes: tuple[int, ...],
) -> None:
    monkeypatch.setitem(
        bcb_series.BCB_SERIES,
        999999,
        BCBSeries(
            metric_id="future_macro_series", sgs_code=999999,
            display_name="Future series", description="Test-only series.",
            unit="units", frequency="monthly", business_domain="Macro",
            source="Banco Central do Brasil - SGS",
        ),
    )
    client = _CreditClient(empty_codes)
    output = tmp_path / "incomplete.parquet"
    with pytest.raises(ValueError, match="20570|21112"):
        build_bcb_credit_silver(
            date(2023, 1, 1), date(2023, 12, 31), client=client,
            bronze_dir=tmp_path / "bronze", output_path=output,
        )
    assert client.requested == [20570, 21112]
    assert not output.exists()
    assert len(list((tmp_path / "bronze").glob("*.json"))) == 4


def test_credit_merge_repetition_preserves_lineage_and_revision_fails() -> None:
    existing = normalize_sgs_payload(
        [{"data": "01/01/2023", "valor": "1800000"}], 20570,
        source_url="https://old.example", retrieved_at="old",
    )
    incoming = existing.assign(source_url="https://new.example", retrieved_at="new")
    merged = merge_macro_indicators(existing, incoming)
    assert len(merged) == 1
    assert merged.iloc[0]["source_url"] == "https://old.example"
    assert merged.iloc[0]["retrieved_at"] == "old"

    conflicting = existing.assign(value=1800001.0)
    with pytest.raises(ValueError, match="existing value=1800000.0, incoming value=1800001.0"):
        merge_macro_indicators(existing, conflicting)


def test_credit_registry_semantics_and_kpi_note() -> None:
    assert set(get_bcb_series(code).sgs_code for code in (1, 432, 1178, 20570, 21112)) == {
        1, 432, 1178, 20570, 21112,
    }
    balance = get_bcb_series(20570)
    npl = get_bcb_series(21112)
    assert balance.metric_id == "household_free_credit_balance"
    assert balance.source_series_id == "bcb_sgs:20570"
    assert balance.unit == "million_brl" and balance.frequency == "monthly"
    assert npl.metric_id == "household_free_credit_npl_90d_rate"
    assert npl.source_series_id == "bcb_sgs:21112"
    assert npl.unit == "percent" and npl.frequency == "monthly"
    dictionary = kpi_dictionary_frame()
    assert dictionary["metric_id"].is_unique
    metrics = set(dictionary["metric_id"])
    assert "household_free_credit_balance" in metrics
    assert "household_free_credit_npl_90d_rate" in metrics
    npl_kpi = dictionary.set_index("metric_id").loc[
        "household_free_credit_npl_90d_rate"
    ]
    assert not bool(npl_kpi["higher_is_better"])
    assert ">90" in npl_kpi["notes"]
    assert "15\u201390" in npl_kpi["notes"]
    assert "not directly comparable" in npl_kpi["notes"].lower()

