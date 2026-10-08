"""Unit tests for Bronze persistence."""

from __future__ import annotations

import json
from pathlib import Path

from meli_intelligence.storage.bronze import (
    save_company_facts_bronze,
)


def test_save_company_facts_bronze(
    tmp_path: Path,
) -> None:
    payload = {
        "cik": 1099590,
        "entityName": "MercadoLibre, Inc.",
        "facts": {
            "us-gaap": {
                "ExampleMetric": {
                    "label": "Example",
                }
            }
        },
    }

    data_path, metadata_path = (
        save_company_facts_bronze(
            payload,
            "1099590",
            bronze_dir=tmp_path,
        )
    )

    assert data_path.exists()
    assert metadata_path.exists()

    stored_payload = json.loads(
        data_path.read_text(encoding="utf-8")
    )

    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )

    assert stored_payload == payload

    assert metadata["source"] == (
        "SEC EDGAR Company Facts API"
    )
    assert metadata["cik"] == "0001099590"
    assert metadata["ingestion_version"] == "1"
    assert metadata["retrieved_at"]
    assert metadata["source_url"].endswith(
        "CIK0001099590.json"
    )


def test_save_company_facts_creates_directories(
    tmp_path: Path,
) -> None:
    bronze_root = tmp_path / "new" / "bronze"

    data_path, _ = save_company_facts_bronze(
        {
            "cik": 1099590,
            "entityName": "MercadoLibre, Inc.",
            "facts": {},
        },
        "1099590",
        bronze_dir=bronze_root,
    )

    assert data_path.parent.exists()
