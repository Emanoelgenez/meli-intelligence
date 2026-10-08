"""Offline tests for BCB Bronze, macro Silver, query and pipeline."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.pipelines.macro_bcb import build_bcb_selic_silver
from meli_intelligence.metadata import bcb_series
from meli_intelligence.metadata.bcb_series import BCBSeries
from meli_intelligence.query.macro import query_macro_indicators
from meli_intelligence.sources.bcb.sgs_client import BCBFetch
from meli_intelligence.storage.bcb_bronze import save_bcb_sgs_bronze
from meli_intelligence.storage.macro import (
    MACRO_INDICATORS_SCHEMA,
    read_macro_indicators,
    validate_macro_indicators,
    merge_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.transformations.bcb_sgs import normalize_sgs_payload


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "metric_id": "selic_target_annual",
            "source_series_id": "bcb_sgs:432",
            "reference_date": date(2023, 1, 2),
            "value": 13.75,
            "unit": "percent_per_year",
            "frequency": "daily",
            "source": "Banco Central do Brasil - SGS",
            "source_url": "https://api.bcb.gov.br/example",
            "retrieved_at": "2026-10-05T00:00:00+00:00",
            "ingestion_version": "1",
        },
    ])


def test_bronze_preserves_raw_payload_and_lineage(tmp_path: Path) -> None:
    raw = b'[{"data":"02/01/2023","valor":"13.75"}]'
    fetch = BCBFetch(
        series_code=432,
        requested_start_date=date(2023, 1, 2),
        requested_end_date=date(2023, 1, 2),
        source_url="https://api.bcb.gov.br/example",
        retrieved_at="2026-10-05T00:00:00+00:00",
        raw_payload=raw,
        records=json.loads(raw),
    )
    raw_path, metadata_path = save_bcb_sgs_bronze(fetch, bronze_dir=tmp_path)
    assert raw_path.read_bytes() == raw
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["provider"] == "BCB"
    assert metadata["dataset"] == "SGS"
    assert metadata["metric_id"] == "selic_target_annual"
    assert metadata["requested_start_date"] == "2023-01-02"
    assert metadata["payload_sha256"]


def test_silver_parquet_roundtrip_schema_and_key_validation(tmp_path: Path) -> None:
    frame = _frame()
    output = tmp_path / "macro" / "macro_indicators.parquet"
    parquet_path, metadata_path = write_macro_indicators(frame, output_path=output)
    restored = read_macro_indicators(parquet_path)
    assert metadata_path.exists()
    assert len(restored) == 1
    assert restored.iloc[0]["value"] == 13.75
    assert list(restored.columns) == MACRO_INDICATORS_SCHEMA.names
    validate_macro_indicators(restored)
    with pytest.raises(ValueError, match="Duplicate macro economic key"):
        validate_macro_indicators(pd.concat([frame, frame], ignore_index=True))


class _StubClient:
    def __init__(self, empty_codes: tuple[int, ...] = ()) -> None:
        self.requested_codes = []
        self.empty_codes = set(empty_codes)

    def fetch_series(self, series_code: int, start_date: date, end_date: date):
        self.requested_codes.append(series_code)
        if series_code in self.empty_codes:
            return [
                BCBFetch(
                    series_code=series_code,
                    requested_start_date=start_date,
                    requested_end_date=end_date,
                    source_url="https://api.bcb.gov.br/example",
                    retrieved_at="2026-10-05T00:00:00+00:00",
                    raw_payload=b"[]",
                    records=[],
                )
            ]
        value = "13.75" if series_code == 432 else "13.65"
        records = [{"data": "02/01/2023", "valor": value}]
        raw = json.dumps(records).encode("utf-8")
        return [
            BCBFetch(
                series_code=series_code,
                requested_start_date=start_date,
                requested_end_date=end_date,
                source_url=(
                    "https://api.bcb.gov.br/dados/serie/"
                    f"bcdata.sgs.{series_code}/dados?formato=json"
                ),
                retrieved_at="2026-10-05T00:00:00+00:00",
                raw_payload=raw,
                records=records,
            )
        ]


def test_pipeline_builds_generic_silver_and_query_filters(tmp_path: Path) -> None:
    client = _StubClient()
    silver, bronze, silver_path, metadata_path = build_bcb_selic_silver(
        date(2023, 1, 1),
        date(2023, 1, 3),
        client=client,
        bronze_dir=tmp_path / "bronze" / "bcb" / "sgs",
        output_path=tmp_path / "silver" / "macro_indicators.parquet",
    )
    assert len(bronze) == 2
    assert client.requested_codes == [432, 1178]
    assert silver_path.exists() and metadata_path.exists()
    assert set(silver["metric_id"]) == {
        "selic_target_annual", "selic_effective_annual_252"
    }
    queried = query_macro_indicators(
        parquet_path=silver_path,
        metric_id="selic_target_annual",
        start_date=date(2023, 1, 2),
        end_date=date(2023, 1, 2),
    )
    assert len(queried) == 1
    assert queried.iloc[0]["value"] == 13.75


def test_pipeline_scope_ignores_future_registry_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        bcb_series.BCB_SERIES,
        999999,
        BCBSeries(
            metric_id="future_macro_series",
            sgs_code=999999,
            display_name="Future series",
            description="Test-only future series.",
            unit="units",
            frequency="daily",
            business_domain="Macro",
            source="Banco Central do Brasil - SGS",
        ),
    )
    client = _StubClient()
    build_bcb_selic_silver(
        date(2023, 1, 1),
        date(2023, 1, 3),
        client=client,
        bronze_dir=tmp_path / "bronze",
        output_path=tmp_path / "silver.parquet",
    )
    assert client.requested_codes == [432, 1178]


@pytest.mark.parametrize(
    ("empty_codes", "missing_code"),
    [((432,), "432"), ((1178,), "1178"), ((432, 1178), "432")],
)
def test_pipeline_fails_if_required_selic_series_is_empty(
    tmp_path: Path,
    empty_codes: tuple[int, ...],
    missing_code: str,
) -> None:
    client = _StubClient(empty_codes=empty_codes)
    output_path = tmp_path / "silver" / "macro_indicators.parquet"
    with pytest.raises(ValueError, match=missing_code):
        build_bcb_selic_silver(
            date(2023, 1, 1),
            date(2023, 1, 3),
            client=client,
            bronze_dir=tmp_path / "bronze",
            output_path=output_path,
        )
    assert client.requested_codes == [432, 1178]
    assert not output_path.exists()


def test_merge_repeated_identical_key_preserves_existing_lineage() -> None:
    existing = _frame()
    incoming = existing.copy()
    incoming["source_url"] = "https://new.example/source"
    incoming["retrieved_at"] = "2026-10-06T00:00:00+00:00"
    merged = merge_macro_indicators(existing, incoming)
    assert len(merged) == 1
    assert merged.iloc[0]["value"] == 13.75
    assert merged.iloc[0]["source_url"] == existing.iloc[0]["source_url"]
    assert merged.iloc[0]["retrieved_at"] == existing.iloc[0]["retrieved_at"]
    assert not merged.duplicated(["metric_id", "reference_date"]).any()


def test_merge_conflicting_value_fails_explicitly() -> None:
    existing = _frame()
    incoming = existing.copy()
    incoming["value"] = 13.5
    with pytest.raises(ValueError, match="Incoming macro values conflict"):
        merge_macro_indicators(existing, incoming)
