"""Tests for Silver financial-fact persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from meli_intelligence.storage.silver import (
    write_financial_facts_parquet,
)


def _sample_row() -> dict:
    return {
        "metric_id": "net_income",
        "taxonomy": "us-gaap",
        "concept": "NetIncomeLoss",
        "unit": "USD",
        "value": 466_000_000,
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
        "reference_year": 2026,
        "period_type": "QUARTER",
        "period_label": "Q2",
        "form": "10-Q",
        "filed_at": "2026-08-06",
        "accession_number": "test-accession",
        "frame": "CY2026Q2",
        "source_fy": 2026,
        "source_fp": "Q2",
        "occurrences": 1,
        "first_reported_value": 466_000_000,
        "first_filed_at": "2026-08-06",
        "first_accession_number": "test-accession",
        "has_value_change": False,
        "value_change": 0,
        "is_derived": False,
    }


def test_write_financial_facts_parquet(
    tmp_path: Path,
) -> None:
    bronze_path = tmp_path / "bronze.json"
    bronze_path.write_text(
        '{"example": true}',
        encoding="utf-8",
    )

    output_path = tmp_path / "financial.parquet"

    parquet_path, metadata_path = (
        write_financial_facts_parquet(
            [_sample_row()],
            entity_cik="0001099590",
            entity_name="MercadoLibre, Inc.",
            output_path=output_path,
            source_bronze_path=bronze_path,
        )
    )

    assert parquet_path.exists()
    assert metadata_path.exists()

    table = pq.read_table(parquet_path)

    assert table.num_rows == 1

    row = table.to_pylist()[0]

    assert row["entity_cik"] == "0001099590"
    assert row["metric_id"] == "net_income"
    assert row["value"] == 466_000_000

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    assert metadata["row_count"] == 1
    assert metadata["schema_version"] == "1"
    assert len(
        metadata["source_bronze_sha256"]
    ) == 64


def test_duplicate_facts_are_rejected(
    tmp_path: Path,
) -> None:
    row = _sample_row()

    with pytest.raises(
        ValueError,
        match="Duplicate canonical",
    ):
        write_financial_facts_parquet(
            [row, row.copy()],
            entity_cik="0001099590",
            entity_name="MercadoLibre, Inc.",
            output_path=(
                tmp_path
                / "financial.parquet"
            ),
        )


def test_invalid_period_type_is_rejected(
    tmp_path: Path,
) -> None:
    row = _sample_row()
    row["period_type"] = "OTHER"

    with pytest.raises(
        ValueError,
        match="invalid period_type",
    ):
        write_financial_facts_parquet(
            [row],
            entity_cik="0001099590",
            entity_name="MercadoLibre, Inc.",
            output_path=(
                tmp_path
                / "financial.parquet"
            ),
        )