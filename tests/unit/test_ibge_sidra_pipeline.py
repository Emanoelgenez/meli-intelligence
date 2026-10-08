"""Offline tests for IBGE SIDRA client, normalization, storage and pipeline."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from meli_intelligence.metadata.ibge_series import (
    IBGE_SERIES,
    SIDRAClassificationFilter,
    get_ibge_series,
)
from meli_intelligence.pipelines.macro_ibge import build_ibge_ipca_silver
from meli_intelligence.query.macro import query_macro_indicators
from meli_intelligence.sources.ibge.sidra_client import SIDRAClient, SIDRAFetch
from meli_intelligence.storage.ibge_bronze import save_ibge_sidra_bronze
from meli_intelligence.storage.macro import (
    MACRO_INDICATORS_SCHEMA,
    merge_macro_indicators,
    read_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.transformations.ibge_sidra import normalize_sidra_payload


def _payload(variable_id: int = 63, values: tuple[tuple[str, str], ...] = (("202301", "0.61"),)) -> list[dict[str, str]]:
    series = get_ibge_series(1737, variable_id)
    # The semantic dimensions intentionally use D9 for variable and D4 for month.
    return [
        {
            "NN": "Nível Territorial", "NC": "Nível Territorial (Código)",
            "V": "Valor", "D4N": "Mês", "D4C": "Mês (Código)",
            "D9N": "Variável", "D9C": "Variável (Código)",
        },
        *[
            {
                "NN": "Brasil", "NC": "1", "V": value,
                "D4N": f"month {period}", "D4C": period,
                "D9N": series.display_name, "D9C": str(variable_id),
            }
            for period, value in values
        ],
    ]


def _frame(variable_id: int = 63, value: float = 0.61) -> pd.DataFrame:
    series = get_ibge_series(1737, variable_id)
    return pd.DataFrame([{
        "metric_id": series.metric_id,
        "source_series_id": series.source_series_id,
        "reference_date": date(2023, 1, 31),
        "value": value,
        "unit": "percent", "frequency": "monthly", "source": "IBGE - SIDRA",
        "source_url": series.source_url(),
        "retrieved_at": "2026-10-05T00:00:00+00:00", "ingestion_version": "1",
    }])


def test_registry_has_only_requested_semantics_and_distinct_metrics() -> None:
    assert {(1737, 63), (1737, 2265)}.issubset(IBGE_SERIES)
    monthly = get_ibge_series(1737, 63)
    annual = get_ibge_series(1737, 2265)
    assert monthly.metric_id == "ipca_monthly_change"
    assert annual.metric_id == "ipca_12m_change"
    assert monthly.unit == annual.unit == "percent"
    assert monthly.frequency == annual.frequency == "monthly"
    assert monthly.business_domain == annual.business_domain == "Macro"
    assert monthly.metric_id != annual.metric_id


def test_economy_registry_has_rolling_unemployment_and_filtered_retail() -> None:
    unemployment = get_ibge_series(6381, 4099)
    retail = get_ibge_series(8880, 11708)
    assert unemployment.metric_id == "unemployment_rate_rolling_3m"
    assert unemployment.source_series_id == "ibge_sidra:6381:4099"
    assert unemployment.frequency == "rolling_3m_monthly"
    assert retail.metric_id == "retail_sales_volume_mom_sa"
    assert retail.source_series_id == "ibge_sidra:8880:11708:retail_volume"
    assert retail.classification_filters == (
        SIDRAClassificationFilter(
            classification_id=11046,
            category_id=56734,
            dimension_name="Tipos de índice",
            category_name="Índice de volume de vendas no comércio varejista",
        ),
    )
    assert unemployment.classification_filters == ()
    assert "/c" not in unemployment.source_url()


@pytest.mark.parametrize("variable_id", [63, 2265])
def test_client_url_p_all_timeout_and_user_agent(variable_id: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_payload(variable_id))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    sidra = SIDRAClient(timeout=12.0, client=client)
    result = sidra.fetch_variable(1737, variable_id)
    request = requests[0]
    assert request.url.path == f"/values/t/1737/n1/all/v/{variable_id}/p/all"
    assert request.headers["user-agent"]
    assert result.records
    assert sidra.timeout == 12.0
    client.close()


def test_client_includes_registry_classification_ids_only_when_configured() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_payload(63))

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    with SIDRAClient(client=http_client) as sidra:
        ipca = sidra.fetch_variable(1737, 63)
        retail = sidra.fetch_variable(8880, 11708)
        unemployment = sidra.fetch_variable(6381, 4099)
    http_client.close()
    assert requests[0].url.path == "/values/t/1737/n1/all/v/63/p/all"
    assert requests[2].url.path == "/values/t/6381/n1/all/v/4099/p/all"
    assert requests[1].url.path == (
        "/values/t/8880/n1/all/v/11708/p/all/c11046/56734"
    )
    assert retail.source_url == str(requests[1].url)
    assert "/c" not in ipca.source_url and "/c" not in unemployment.source_url


def test_client_http_error_json_error_and_invalid_shape() -> None:
    def http_error(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    sidra = SIDRAClient(client=httpx.Client(transport=httpx.MockTransport(http_error)))
    with pytest.raises(httpx.HTTPStatusError):
        sidra.fetch_variable(1737, 63)
    sidra._client.close()

    def invalid_json(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    sidra = SIDRAClient(client=httpx.Client(transport=httpx.MockTransport(invalid_json)))
    with pytest.raises(ValueError, match="invalid JSON"):
        sidra.fetch_variable(1737, 63)
    sidra._client.close()

    def invalid_shape(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "object"})

    sidra = SIDRAClient(client=httpx.Client(transport=httpx.MockTransport(invalid_shape)))
    with pytest.raises(ValueError, match="array"):
        sidra.fetch_variable(1737, 63)
    sidra._client.close()


def test_transformation_header_driven_month_ends_sign_and_sorting() -> None:
    payload = _payload(63, (("202402", "-0.31"), ("202301", "0.61")))
    frame = normalize_sidra_payload(
        payload, 1737, 63, source_url="https://sidra", retrieved_at="now"
    )
    assert list(frame["reference_date"]) == [date(2023, 1, 31), date(2024, 2, 29)]
    assert frame.iloc[0]["value"] == 0.61
    assert frame.iloc[1]["value"] == -0.31
    assert frame.iloc[0]["source_series_id"] == "ibge_sidra:1737:63"


@pytest.mark.parametrize(
    ("period", "value", "message"),
    [("202313", "1", "period"), ("202301", "X", "non-numeric value"),
     ("202301", "", "empty value"), ("202301", " ", "empty value")],
)
def test_transformation_rejects_invalid_period_or_values(period: str, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_sidra_payload(
            _payload(63, ((period, value),)), 1737, 63,
            source_url="https://sidra", retrieved_at="now",
        )


@pytest.mark.parametrize("marker", ["...", ".."])
def test_sidra_unavailable_and_not_applicable_values_are_omitted(marker: str) -> None:
    frame = normalize_sidra_payload(
        _payload(63, (("202301", marker),)), 1737, 63,
        source_url="https://sidra", retrieved_at="now",
    )
    assert frame.empty
    assert "value" in frame.columns
    assert not frame["value"].isna().any()


@pytest.mark.parametrize("zero", ["-", "0"])
def test_sidra_zero_markers_normalize_to_numeric_zero(zero: str) -> None:
    frame = normalize_sidra_payload(
        _payload(63, (("202301", zero),)), 1737, 63,
        source_url="https://sidra", retrieved_at="now",
    )
    assert len(frame) == 1
    assert frame.iloc[0]["value"] == 0.0


def test_sidra_unavailable_marker_is_skipped_beside_numeric_observation() -> None:
    frame = normalize_sidra_payload(
        _payload(63, (("202301", "..."), ("202302", "0.4"))),
        1737, 63, source_url="https://sidra", retrieved_at="now",
    )
    assert frame[["reference_date", "value"]].to_dict(orient="records") == [
        {"reference_date": date(2023, 2, 28), "value": 0.4}
    ]
    assert not frame["value"].isna().any()


def test_transformation_rejects_semantic_mismatch_and_duplicate() -> None:
    invalid = _payload(63)
    invalid[1]["D9N"] = get_ibge_series(1737, 2265).display_name
    with pytest.raises(ValueError, match="label"):
        normalize_sidra_payload(invalid, 1737, 63, source_url="u", retrieved_at="t")
    duplicate = _payload(63, (("202301", "0.61"), ("202301", "0.61")))
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_sidra_payload(duplicate, 1737, 63, source_url="u", retrieved_at="t")


def _economy_payload(table_id: int, variable_id: int, values: tuple[tuple[str, str, str], ...]) -> list[dict[str, str]]:
    series = get_ibge_series(table_id, variable_id)
    header = {
        "NN": "Nível Territorial", "NC": "Nível Territorial (Código)",
        "V": "Valor", "D7N": "Mês", "D7C": "Mês (Código)",
        "D2N": "Variável", "D2C": "Variável (Código)",
    }
    if table_id == 8880:
        header.update({"D9N": "Tipos de índice", "D9C": "Tipos de índice (Código)"})
    rows = []
    for period, value, category in values:
        row = {
            "NN": "Brasil", "NC": "1", "V": value,
            "D7N": f"month {period}", "D7C": period,
            "D2N": series.display_name, "D2C": str(variable_id),
        }
        if table_id == 8880:
            row.update({
                "D9N": category,
                "D9C": "56734" if category.startswith("Índice de volume") else "56735",
            })
        rows.append(row)
    return [header, *rows]


def test_retail_classification_filter_uses_semantic_header_not_dimension_position() -> None:
    volume = "Índice de volume de vendas no comércio varejista"
    revenue = "Índice de receita nominal de vendas no comércio varejista"
    payload = _economy_payload(8880, 11708, (
        ("202301", "0.4", revenue), ("202301", "0.2", volume),
        ("202302", "0.3", volume),
    ))
    frame = normalize_sidra_payload(
        payload, 8880, 11708, source_url="u", retrieved_at="t"
    )
    assert frame["value"].tolist() == [0.2, 0.3]
    assert frame["reference_date"].tolist() == [date(2023, 1, 31), date(2023, 2, 28)]
    assert frame["source_series_id"].eq("ibge_sidra:8880:11708:retail_volume").all()


def test_retail_classification_missing_or_ambiguous_fails() -> None:
    volume = "Índice de volume de vendas no comércio varejista"
    payload = _economy_payload(8880, 11708, (("202301", "0.2", "other"),))
    with pytest.raises(ValueError, match="category.*not found"):
        normalize_sidra_payload(payload, 8880, 11708, source_url="u", retrieved_at="t")

    payload = _economy_payload(8880, 11708, (("202301", "0.2", volume),))
    payload[0]["D6N"] = "Tipo de índice"
    payload[0]["D6C"] = "Tipo de índice (Código)"
    with pytest.raises(ValueError, match="exactly one classification dimension"):
        normalize_sidra_payload(payload, 8880, 11708, source_url="u", retrieved_at="t")

    payload = _economy_payload(8880, 11708, (("202301", "0.2", volume),))
    payload[0]["D9N"] = "Forma de apresentação"
    payload[0]["D9C"] = "Forma de apresentação (Código)"
    with pytest.raises(ValueError, match="exactly one classification dimension"):
        normalize_sidra_payload(payload, 8880, 11708, source_url="u", retrieved_at="t")

    payload = _economy_payload(8880, 11708, (
        ("202301", "0.2", volume), ("202302", "0.3", volume),
    ))
    payload[2]["D9C"] = "different-code"
    with pytest.raises(ValueError, match="category.*ambiguous"):
        normalize_sidra_payload(payload, 8880, 11708, source_url="u", retrieved_at="t")


def test_unemployment_is_rolling_three_month_with_terminal_month_reference() -> None:
    payload = _economy_payload(6381, 4099, (("202312", "7.4", ""),))
    frame = normalize_sidra_payload(
        payload, 6381, 4099, source_url="u", retrieved_at="t"
    )
    assert frame.iloc[0]["reference_date"] == date(2023, 12, 31)
    assert frame.iloc[0]["frequency"] == "rolling_3m_monthly"
    assert frame.iloc[0]["value"] == 7.4
    duplicate = _economy_payload(6381, 4099, (
        ("202312", "7.4", ""), ("202312", "7.4", ""),
    ))
    with pytest.raises(ValueError, match="Duplicate macro economic key"):
        normalize_sidra_payload(
            duplicate, 6381, 4099, source_url="u", retrieved_at="t"
        )


def test_bronze_preserves_bytes_hash_metadata_and_refuses_overwrite(tmp_path: Path) -> None:
    raw = json.dumps(_payload(63)).encode()
    fetch = SIDRAFetch(1737, 63, "https://sidra", "2026-10-05T00:00:00+00:00", raw, _payload())
    payload_path, metadata_path = save_ibge_sidra_bronze(fetch, bronze_dir=tmp_path)
    assert payload_path.read_bytes() == raw
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert meta["payload_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (meta["table_id"], meta["variable_id"], meta["metric_id"]) == (1737, 63, "ipca_monthly_change")
    with pytest.raises(FileExistsError):
        save_ibge_sidra_bronze(fetch, bronze_dir=tmp_path)


def test_silver_bcb_and_ibge_coexist_and_merge_revision_safety(tmp_path: Path) -> None:
    ibge = _frame()
    bcb = ibge.assign(
        metric_id="selic_target_annual", source_series_id="bcb_sgs:432",
        value=13.75, unit="percent_per_year", frequency="daily",
        source="Banco Central do Brasil - SGS", source_url="https://bcb",
    )
    path = tmp_path / "macro.parquet"
    write_macro_indicators(pd.concat([ibge, bcb], ignore_index=True), output_path=path)
    restored = read_macro_indicators(path)
    assert set(restored["source_series_id"]) == {"ibge_sidra:1737:63", "bcb_sgs:432"}
    assert list(restored.columns) == MACRO_INDICATORS_SCHEMA.names
    queried = query_macro_indicators(parquet_path=path)
    assert set(queried["metric_id"]) == {"ipca_monthly_change", "selic_target_annual"}
    incoming = ibge.assign(source_url="https://re-fetch", retrieved_at="later")
    merged = merge_macro_indicators(ibge, incoming)
    assert len(merged) == 1 and merged.iloc[0]["source_url"] == ibge.iloc[0]["source_url"]
    with pytest.raises(ValueError, match="existing value=0.61, incoming value=0.7"):
        merge_macro_indicators(ibge, ibge.assign(value=0.7))


class _StubSIDRA:
    def __init__(self, empty: tuple[int, ...] = ()) -> None:
        self.requested: list[tuple[int, int]] = []
        self.requested_classifications = []
        self.empty = set(empty)

    def fetch_variable(self, table_id: int, variable_id: int, *, classification_filters=()) -> SIDRAFetch:
        self.requested.append((table_id, variable_id))
        self.requested_classifications.append(classification_filters)
        records = [] if variable_id in self.empty else _payload(variable_id, (
            ("202301", "0.61"), ("202304", "0.61"),
            ("202312", "4.62" if variable_id == 2265 else "0.56"),
        ))
        return SIDRAFetch(table_id, variable_id, get_ibge_series(table_id, variable_id).source_url(classification_filters=classification_filters),
                          "2026-10-05T00:00:00+00:00", json.dumps(records).encode(), records)

    def close(self) -> None:
        pass


def test_pipeline_scope_filter_month_end_query_and_empty_guard(tmp_path: Path) -> None:
    client = _StubSIDRA()
    silver, _, path, _ = build_ibge_ipca_silver(
        date(2023, 1, 1), date(2023, 12, 31), client=client,
        bronze_dir=tmp_path / "bronze", output_path=tmp_path / "macro.parquet",
    )
    assert client.requested == [(1737, 63), (1737, 2265)]
    assert client.requested_classifications == [(), ()]
    assert silver.groupby("metric_id").size().to_dict() == {
        "ipca_12m_change": 3, "ipca_monthly_change": 3,
    }
    assert query_macro_indicators(parquet_path=path, metric_id="ipca_monthly_change").shape[0] == 3
    assert silver.loc[silver.metric_id == "ipca_monthly_change", "reference_date"].min() == date(2023, 1, 31)

    for empty in ((63,), (63, 2265)):
        empty_client = _StubSIDRA(empty=empty)
        empty_output = tmp_path / f"incomplete-{len(empty)}.parquet"
        with pytest.raises(ValueError, match="ipca_monthly_change"):
            build_ibge_ipca_silver(client=empty_client, bronze_dir=tmp_path / f"empty-bronze-{len(empty)}", output_path=empty_output)
        assert empty_client.requested == [(1737, 63), (1737, 2265)]
        assert not empty_output.exists()
