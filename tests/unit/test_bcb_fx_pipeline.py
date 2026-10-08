"""Offline tests for the BCB SGS USD/BRL macro slice."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.metadata import bcb_series
from meli_intelligence.metadata.bcb_series import BCBSeries
from meli_intelligence.pipelines.macro_bcb_fx import (
    USD_BRL_SERIES_CODES,
    build_bcb_usd_brl_silver,
)
from meli_intelligence.query.macro import query_macro_indicators
from meli_intelligence.sources.bcb.sgs_client import BCBFetch
from meli_intelligence.storage.macro import (
    read_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.transformations.bcb_sgs import normalize_sgs_payload


def _fetch(
    series_code: int,
    start_date: date,
    end_date: date,
    records: list[dict[str, str]] | None = None,
) -> BCBFetch:
    observations = records if records is not None else [
        {"data": "03/01/2023", "valor": "5.1234"}
    ]
    raw = json.dumps(observations).encode("utf-8")
    return BCBFetch(
        series_code=series_code,
        requested_start_date=start_date,
        requested_end_date=end_date,
        source_url=(
            "https://api.bcb.gov.br/dados/serie/"
            f"bcdata.sgs.{series_code}/dados?formato=json"
        ),
        retrieved_at="2026-10-05T00:00:00+00:00",
        raw_payload=raw,
        records=observations,
    )


class _StubBCBClient:
    def __init__(self, *, empty: bool = False) -> None:
        self.requested_codes: list[int] = []
        self.empty = empty

    def fetch_series(self, series_code: int, start_date: date, end_date: date):
        self.requested_codes.append(series_code)
        return [_fetch(series_code, start_date, end_date, [] if self.empty else None)]

    def close(self) -> None:
        pass


def _existing_multi_source_frame(*, include_fx: bool = False) -> pd.DataFrame:
    metrics = [
        ("selic_target_annual", "bcb_sgs:432", 13.75, "percent_per_year", "daily", "Banco Central do Brasil - SGS"),
        ("selic_effective_annual_252", "bcb_sgs:1178", 13.65, "percent_per_year", "daily", "Banco Central do Brasil - SGS"),
        ("ipca_monthly_change", "ibge_sidra:1737:63", 0.62, "percent", "monthly", "IBGE - SIDRA"),
        ("ipca_12m_change", "ibge_sidra:1737:2265", 5.77, "percent", "monthly", "IBGE - SIDRA"),
    ]
    rows = [
        {
            "metric_id": metric_id,
            "source_series_id": source_series_id,
            "reference_date": date(2023, 1, 2),
            "value": value,
            "unit": unit,
            "frequency": frequency,
            "source": source,
            "source_url": "https://source.example/retained",
            "retrieved_at": "2023-02-01T00:00:00+00:00",
            "ingestion_version": "1",
        }
        for metric_id, source_series_id, value, unit, frequency, source in metrics
    ]
    if include_fx:
        rows.append({
            "metric_id": "usd_brl_sell_rate",
            "source_series_id": "bcb_sgs:1",
            "reference_date": date(2023, 1, 3),
            "value": 5.1234,
            "unit": "brl_per_usd",
            "frequency": "daily",
            "source": "Banco Central do Brasil - SGS",
            "source_url": "https://source.example/retained",
            "retrieved_at": "2023-02-01T00:00:00+00:00",
            "ingestion_version": "1",
        })
    return pd.DataFrame(rows)


def test_fx_pipeline_scope_bronze_silver_coexistence_and_query(
    tmp_path: Path,
) -> None:
    assert USD_BRL_SERIES_CODES == (1,)
    output_path = tmp_path / "macro_indicators.parquet"
    write_macro_indicators(_existing_multi_source_frame(), output_path=output_path)
    client = _StubBCBClient()
    silver, bronze, silver_path, metadata_path = build_bcb_usd_brl_silver(
        date(2023, 1, 1), date(2023, 12, 31), client=client,
        bronze_dir=tmp_path / "bronze", output_path=output_path,
    )
    assert client.requested_codes == [1]
    assert len(bronze) == 1 and all(path.exists() for path in bronze[0])
    metadata = json.loads(bronze[0][1].read_text(encoding="utf-8"))
    assert metadata["series_code"] == 1
    assert metadata["metric_id"] == "usd_brl_sell_rate"
    assert metadata["source_url"] == _fetch(1, date(2023, 1, 1), date(2023, 12, 31)).source_url
    assert metadata["requested_start_date"] == "2023-01-01"
    assert metadata["requested_end_date"] == "2023-12-31"
    assert metadata["retrieved_at"] == "2026-10-05T00:00:00+00:00"
    assert metadata["ingestion_version"] == "1"
    assert metadata["payload_sha256"]
    assert silver_path.exists() and metadata_path.exists()
    assert set(silver["metric_id"]) == {
        "selic_target_annual", "selic_effective_annual_252",
        "ipca_monthly_change", "ipca_12m_change", "usd_brl_sell_rate",
    }
    assert silver["source_series_id"].eq("bcb_sgs:1").sum() == 1
    assert "series_code" not in read_macro_indicators(silver_path).columns
    result = query_macro_indicators(
        parquet_path=silver_path,
        metric_id="usd_brl_sell_rate",
        start_date=date(2023, 1, 3),
        end_date=date(2023, 1, 3),
    )
    assert len(result) == 1
    assert result.iloc[0]["value"] == 5.1234
    assert result.iloc[0]["source_series_id"] == "bcb_sgs:1"
    assert result.iloc[0]["source_url"] == _fetch(
        1, date(2023, 1, 1), date(2023, 12, 31)
    ).source_url


def test_fx_pipeline_repeated_observation_preserves_lineage(tmp_path: Path) -> None:
    output_path = tmp_path / "macro_indicators.parquet"
    write_macro_indicators(
        _existing_multi_source_frame(include_fx=True), output_path=output_path
    )
    silver, _, _, _ = build_bcb_usd_brl_silver(
        date(2023, 1, 1), date(2023, 12, 31),
        client=_StubBCBClient(), bronze_dir=tmp_path / "bronze",
        output_path=output_path,
    )
    fx = silver.loc[silver["metric_id"] == "usd_brl_sell_rate"].iloc[0]
    assert fx["source_url"] == "https://source.example/retained"
    assert fx["retrieved_at"] == "2023-02-01T00:00:00+00:00"


def test_fx_revision_conflict_does_not_overwrite_silver(tmp_path: Path) -> None:
    output_path = tmp_path / "macro_indicators.parquet"
    existing = _existing_multi_source_frame(include_fx=True)
    existing.loc[existing["metric_id"] == "usd_brl_sell_rate", "value"] = 5.0
    write_macro_indicators(existing, output_path=output_path)
    with pytest.raises(
        ValueError,
        match="metric_id='usd_brl_sell_rate'.*existing value=5.0, incoming value=5.1234",
    ):
        build_bcb_usd_brl_silver(
            date(2023, 1, 1), date(2023, 12, 31),
            client=_StubBCBClient(), bronze_dir=tmp_path / "bronze",
            output_path=output_path,
        )
    restored = read_macro_indicators(output_path)
    assert restored.loc[restored["metric_id"] == "usd_brl_sell_rate", "value"].iloc[0] == 5.0


def test_fx_pipeline_does_not_expand_with_registry_and_rejects_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        bcb_series.BCB_SERIES,
        999999,
        BCBSeries(
            metric_id="future_macro_series", sgs_code=999999,
            display_name="Future series", description="Test-only series.",
            unit="units", frequency="daily", business_domain="Macro",
            source="Banco Central do Brasil - SGS",
        ),
    )
    client = _StubBCBClient(empty=True)
    output_path = tmp_path / "incomplete.parquet"
    with pytest.raises(ValueError, match=r"series 1 \(usd_brl_sell_rate\)"):
        build_bcb_usd_brl_silver(
            date(2023, 1, 1), date(2023, 1, 3), client=client,
            bronze_dir=tmp_path / "bronze", output_path=output_path,
        )
    assert client.requested_codes == [1]
    assert not output_path.exists()
    assert len(list((tmp_path / "bronze").glob("*.json"))) == 2


def test_fx_transformer_lineage_and_order() -> None:
    frame = normalize_sgs_payload(
        [
            {"data": "04/01/2023", "valor": "5.2"},
            {"data": "03/01/2023", "valor": "5.1234"},
        ],
        1,
        source_url="https://api.bcb.gov.br/example",
        retrieved_at="2026-10-05T00:00:00+00:00",
    )
    assert frame["reference_date"].tolist() == [date(2023, 1, 3), date(2023, 1, 4)]
    assert frame["value"].tolist() == [5.1234, 5.2]
    assert set(frame["source_series_id"]) == {"bcb_sgs:1"}
    assert set(frame["unit"]) == {"brl_per_usd"}
    assert set(frame["frequency"]) == {"daily"}
