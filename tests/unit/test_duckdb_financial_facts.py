"""Tests for DuckDB financial queries."""

from __future__ import annotations

from pathlib import Path

from meli_intelligence.query.duckdb import (
    financial_facts_summary,
    query_financial_facts,
)
from meli_intelligence.storage.silver import (
    write_financial_facts_parquet,
)


def _row(
    metric_id: str,
    period_type: str,
    start: str | None,
    end: str,
    value: int,
    label: str,
) -> dict:
    return {
        "metric_id": metric_id,
        "taxonomy": "us-gaap",
        "concept": metric_id,
        "unit": "USD",
        "value": value,
        "period_start": start,
        "period_end": end,
        "reference_year": int(end[:4]),
        "period_type": period_type,
        "period_label": label,
        "form": "10-Q",
        "filed_at": "2026-08-06",
        "accession_number": (
            f"{metric_id}-{end}"
        ),
        "frame": None,
        "source_fy": 2026,
        "source_fp": label,
        "occurrences": 1,
        "first_reported_value": value,
        "first_filed_at": "2026-08-06",
        "first_accession_number": (
            f"{metric_id}-{end}"
        ),
        "has_value_change": False,
        "value_change": 0,
        "is_derived": False,
    }


def test_query_financial_facts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "facts.parquet"

    rows = [
        _row(
            "net_income",
            "QUARTER",
            "2026-01-01",
            "2026-03-31",
            417,
            "Q1",
        ),
        _row(
            "net_income",
            "QUARTER",
            "2026-04-01",
            "2026-06-30",
            466,
            "Q2",
        ),
        _row(
            "gross_profit",
            "QUARTER",
            "2026-04-01",
            "2026-06-30",
            4_159,
            "Q2",
        ),
    ]

    write_financial_facts_parquet(
        rows,
        entity_cik="0001099590",
        entity_name="MercadoLibre, Inc.",
        output_path=path,
    )

    result = query_financial_facts(
        parquet_path=path,
        metric_id="net_income",
        period_type="QUARTER",
        min_reference_year=2026,
    )

    assert len(result) == 2
    assert list(result["value"]) == [
        417,
        466,
    ]


def test_financial_facts_summary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "facts.parquet"

    rows = [
        _row(
            "net_income",
            "QUARTER",
            "2026-01-01",
            "2026-03-31",
            417,
            "Q1",
        ),
        _row(
            "net_income",
            "QUARTER",
            "2026-04-01",
            "2026-06-30",
            466,
            "Q2",
        ),
    ]

    write_financial_facts_parquet(
        rows,
        entity_cik="0001099590",
        entity_name="MercadoLibre, Inc.",
        output_path=path,
    )

    summary = financial_facts_summary(
        parquet_path=path
    )

    assert len(summary) == 1
    assert summary.iloc[0]["observations"] == 2