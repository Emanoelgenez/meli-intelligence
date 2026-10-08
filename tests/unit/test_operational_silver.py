"""Tests for operational KPI Silver canonicalization."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.storage.operational_silver import (
    canonicalize_operational_rows,
)


def _row(
    *,
    definition: str,
    filing_date: str,
    value: float,
    accession: str,
) -> dict:
    return {
        "metric_id": "gmv",
        "unit": "USD",
        "value": value,
        "period_start": "2025-04-01",
        "period_end": "2025-06-30",
        "definition_version": definition,
        "filing_date": filing_date,
        "accession_number": accession,
        "is_comparative": (
            filing_date
            != "2025-08-04"
        ),
        "release_reference_period": (
            "2025-06-30"
        ),
        "sec_report_date": filing_date,
    }


def test_latest_filing_wins_within_definition() -> None:
    frame = pd.DataFrame(
        [
            _row(
                definition="v2_food_delivery",
                filing_date="2025-08-04",
                value=100.0,
                accession="001",
            ),
            _row(
                definition="v2_food_delivery",
                filing_date="2026-08-05",
                value=101.0,
                accession="002",
            ),
        ]
    )

    result = canonicalize_operational_rows(
        frame
    )

    assert len(result) == 1

    row = result.iloc[0]

    assert row["value"] == 101.0
    assert row["occurrences"] == 2
    assert row["first_reported_value"] == 100.0
    assert bool(row["has_value_change"])
    assert row["value_change"] == 1.0
    assert bool(row["source_is_comparative"])


def test_definition_versions_are_not_collapsed() -> None:
    frame = pd.DataFrame(
        [
            _row(
                definition="v1_marketplace_only",
                filing_date="2025-08-04",
                value=100.0,
                accession="001",
            ),
            _row(
                definition="v2_food_delivery",
                filing_date="2026-08-05",
                value=101.0,
                accession="002",
            ),
        ]
    )

    result = canonicalize_operational_rows(
        frame
    )

    assert len(result) == 2

    assert set(
        result[
            "definition_version"
        ]
    ) == {
        "v1_marketplace_only",
        "v2_food_delivery",
    }