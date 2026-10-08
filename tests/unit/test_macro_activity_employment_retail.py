"""Offline coverage for the Sprint 3E macro signals and fixed pipelines."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.metadata.bcb_series import BCB_SERIES, get_bcb_series
from meli_intelligence.metadata.ibge_series import get_ibge_series
from meli_intelligence.metadata.kpi_dictionary import kpi_dictionary_frame
from meli_intelligence.pipelines.macro_bcb_activity import (
    ACTIVITY_SERIES_CODES,
    build_bcb_activity_silver,
)
from meli_intelligence.pipelines.macro_ibge_economy import (
    ECONOMY_SERIES,
    build_ibge_economy_silver,
)
from meli_intelligence.query.macro import query_macro_indicators
from meli_intelligence.sources.bcb.sgs_client import BCBFetch
from meli_intelligence.sources.ibge.sidra_client import SIDRAFetch
from meli_intelligence.storage.macro import read_macro_indicators, write_macro_indicators


def _sidra_payload(table_id: int, variable_id: int) -> list[dict[str, str]]:
    series = get_ibge_series(table_id, variable_id)
    header = {
        "V": "Valor", "NC": "Nível Territorial (Código)",
        "NN": "Nível Territorial", "D4C": "Mês (Código)", "D4N": "Mês",
        "D8C": "Variável (Código)", "D8N": "Variável",
    }
    if table_id == 8880:
        header.update({"D2C": "Tipos de índice (Código)", "D2N": "Tipos de índice"})
    row = {
        "V": "7.4" if table_id == 6381 else "0.2", "NC": "1", "NN": "Brasil",
        "D4C": "202312", "D4N": "Dezembro 2023",
        "D8C": str(variable_id), "D8N": series.display_name,
    }
    if table_id == 8880:
        row.update({
            "D2C": "56734", "D2N": "Índice de volume de vendas no comércio varejista",
        })
    return [header, row]


class _SIDRAStub:
    def __init__(self, *, empty_variable: int | None = None) -> None:
        self.requested: list[tuple[int, int]] = []
        self.requested_classifications = []
        self.empty_variable = empty_variable

    def fetch_variable(self, table_id: int, variable_id: int, *, classification_filters=()) -> SIDRAFetch:
        self.requested.append((table_id, variable_id))
        self.requested_classifications.append(classification_filters)
        records = [] if variable_id == self.empty_variable else _sidra_payload(table_id, variable_id)
        return SIDRAFetch(
            table_id, variable_id, get_ibge_series(table_id, variable_id).source_url(classification_filters=classification_filters),
            "2026-10-05T00:00:00+00:00", json.dumps(records).encode(), records,
        )

    def close(self) -> None:
        pass


class _BCBStub:
    def __init__(self) -> None:
        self.requested: list[int] = []

    def fetch_series(self, code: int, start: date, end: date) -> list[BCBFetch]:
        self.requested.append(code)
        return [BCBFetch(
            code, start, end, "https://bcb/series", "2026-10-05T00:00:00+00:00",
            b'[{"data":"01/12/2023","valor":"151.2"}]',
            [{"data": "01/12/2023", "valor": "151.2"}],
        )]

    def close(self) -> None:
        pass


def test_fixed_activity_scope_bronze_and_month_end_pipeline(tmp_path: Path) -> None:
    client = _BCBStub()
    frame, bronze_paths, silver_path, _ = build_bcb_activity_silver(
        date(2023, 1, 1), date(2023, 12, 31), client=client,
        bronze_dir=tmp_path / "bcb", output_path=tmp_path / "macro.parquet",
    )
    assert ACTIVITY_SERIES_CODES == (24364,)
    assert client.requested == [24364]
    assert len(bronze_paths) == 1 and bronze_paths[0][0].exists()
    assert frame.iloc[0]["metric_id"] == "ibc_br_activity_sa_index"
    assert frame.iloc[0]["source_series_id"] == "bcb_sgs:24364"
    assert frame.iloc[0]["reference_date"] == date(2023, 12, 31)
    assert silver_path.exists()
    queried = query_macro_indicators(
        parquet_path=silver_path, metric_id="ibc_br_activity_sa_index",
        start_date=date(2023, 12, 1), end_date=date(2023, 12, 31),
    )
    assert len(queried) == 1
    assert queried.iloc[0]["source_series_id"] == "bcb_sgs:24364"
    assert get_bcb_series(24364).unit == "index"


def test_ibge_economy_pipeline_fixed_scope_and_month_filter(tmp_path: Path) -> None:
    client = _SIDRAStub()
    frame, bronze_paths, _, _ = build_ibge_economy_silver(
        date(2023, 12, 1), date(2023, 12, 31), client=client,
        bronze_dir=tmp_path / "ibge", output_path=tmp_path / "macro.parquet",
    )
    assert ECONOMY_SERIES == ((6381, 4099), (8880, 11708))
    assert client.requested == [(6381, 4099), (8880, 11708)]
    assert client.requested_classifications == [(), get_ibge_series(8880, 11708).classification_filters]
    assert len(bronze_paths) == 2 and all(data.exists() for data, _ in bronze_paths)
    retail_metadata = json.loads(bronze_paths[1][1].read_text(encoding="utf-8"))
    assert "/c11046/56734" in retail_metadata["source_url"]
    assert set(frame["metric_id"]) == {
        "unemployment_rate_rolling_3m", "retail_sales_volume_mom_sa",
    }
    assert set(frame["reference_date"]) == {date(2023, 12, 31)}
    assert len(frame) == 2
    unemployment_query = query_macro_indicators(
        parquet_path=tmp_path / "macro.parquet",
        metric_id="unemployment_rate_rolling_3m",
        start_date=date(2023, 12, 1), end_date=date(2023, 12, 31),
    )
    retail_query = query_macro_indicators(
        parquet_path=tmp_path / "macro.parquet",
        metric_id="retail_sales_volume_mom_sa",
        start_date=date(2023, 12, 1), end_date=date(2023, 12, 31),
    )
    assert len(unemployment_query) == len(retail_query) == 1
    assert unemployment_query.iloc[0]["reference_date"].date() == date(2023, 12, 31)
    assert retail_query.iloc[0]["reference_date"].date() == date(2023, 12, 31)


def _assert_empty_metric_fails_without_silver(
    tmp_path: Path, *, empty_variable: int, expected_metric_id: str,
) -> None:
    client = _SIDRAStub(empty_variable=empty_variable)
    output = tmp_path / f"missing-{empty_variable}.parquet"
    with pytest.raises(ValueError, match=expected_metric_id):
        build_ibge_economy_silver(
            date(2023, 1, 1), date(2023, 12, 31), client=client,
            bronze_dir=tmp_path / f"empty-bronze-{empty_variable}", output_path=output,
        )
    assert client.requested == [(6381, 4099), (8880, 11708)]
    assert not output.exists()
    assert not Path(str(output) + ".metadata.json").exists()


def test_empty_unemployment_series_error_names_metric_and_does_not_persist_silver(tmp_path: Path) -> None:
    _assert_empty_metric_fails_without_silver(
        tmp_path, empty_variable=4099,
        expected_metric_id="unemployment_rate_rolling_3m",
    )


def test_empty_retail_series_error_names_metric_and_does_not_persist_silver(tmp_path: Path) -> None:
    _assert_empty_metric_fails_without_silver(
        tmp_path, empty_variable=11708,
        expected_metric_id="retail_sales_volume_mom_sa",
    )


def test_kpi_dictionary_contains_activity_employment_retail_metrics() -> None:
    frame = kpi_dictionary_frame()
    assert frame["metric_id"].is_unique
    metrics = set(frame["metric_id"])
    assert {
        "unemployment_rate_rolling_3m",
        "ibc_br_activity_sa_index",
        "retail_sales_volume_mom_sa",
    }.issubset(metrics)
    rows = frame.set_index("metric_id")
    assert rows.loc["unemployment_rate_rolling_3m", "frequency"] == "rolling_3m_monthly"
    assert rows.loc["unemployment_rate_rolling_3m", "higher_is_better"] is False
    assert rows.loc["ibc_br_activity_sa_index", "higher_is_better"] is None
    assert rows.loc["retail_sales_volume_mom_sa", "higher_is_better"] is None


def test_all_ten_macro_metrics_coexist_in_shared_silver_and_query(tmp_path: Path) -> None:
    identities = [
        ("selic_target_annual", "bcb_sgs:432", "percent_per_year", "daily"),
        ("selic_effective_annual_252", "bcb_sgs:1178", "percent_per_year", "daily"),
        ("ipca_monthly_change", "ibge_sidra:1737:63", "percent", "monthly"),
        ("ipca_12m_change", "ibge_sidra:1737:2265", "percent", "monthly"),
        ("usd_brl_sell_rate", "bcb_sgs:1", "brl_per_usd", "daily"),
        ("household_free_credit_balance", "bcb_sgs:20570", "million_brl", "monthly"),
        ("household_free_credit_npl_90d_rate", "bcb_sgs:21112", "percent", "monthly"),
        ("unemployment_rate_rolling_3m", "ibge_sidra:6381:4099", "percent", "rolling_3m_monthly"),
        ("ibc_br_activity_sa_index", "bcb_sgs:24364", "index", "monthly"),
        ("retail_sales_volume_mom_sa", "ibge_sidra:8880:11708:retail_volume", "percent", "monthly"),
    ]
    frame = pd.DataFrame([
        {
            "metric_id": metric_id, "source_series_id": source_series_id,
            "reference_date": date(2023, 12, 31), "value": 1.0,
            "unit": unit, "frequency": frequency, "source": "official",
            "source_url": "https://example.invalid", "retrieved_at": "2026-10-05T00:00:00+00:00",
            "ingestion_version": "1",
        }
        for metric_id, source_series_id, unit, frequency in identities
    ])
    path = tmp_path / "all-macro.parquet"
    write_macro_indicators(frame, output_path=path)
    restored = read_macro_indicators(path)
    queried = query_macro_indicators(parquet_path=path)
    assert set(restored["metric_id"]) == {row[0] for row in identities}
    assert restored["source_series_id"].is_unique
    assert restored[["metric_id", "reference_date"]].duplicated().sum() == 0
    assert "series_code" not in restored.columns
    assert set(queried["metric_id"]) == {row[0] for row in identities}
