"""DuckDB read helpers for Macro Analytics and observation Gold Parquet."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.storage.macro_analytics import (
    DEFAULT_MACRO_ANALYTICS_PATH,
    DEFAULT_MACRO_EVIDENCE_PATH,
)


def _query(
    path: Path,
    *,
    metric_id: str | None,
    start_date: date | None,
    end_date: date | None,
    evidence: bool,
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Macro Gold Parquet not found: {path}")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    conditions = []
    parameters: list[object] = [str(path)]
    if metric_id is not None:
        conditions.append("metric_id = ?")
        parameters.append(metric_id)
    if start_date is not None:
        conditions.append("reference_date >= ?")
        parameters.append(start_date)
    if end_date is not None:
        conditions.append("reference_date <= ?")
        parameters.append(end_date)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    ordering = "reference_date, evidence_id" if evidence else "reference_date, metric_id"
    connection = duckdb.connect(database=":memory:")
    try:
        return connection.execute(
            f"SELECT * FROM read_parquet(?) {where} ORDER BY {ordering}",
            parameters,
        ).df()
    finally:
        connection.close()


def query_macro_analytics(
    *,
    path: Path = DEFAULT_MACRO_ANALYTICS_PATH,
    metric_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Query derived macro indicators by metric and economic date."""
    return _query(path, metric_id=metric_id, start_date=start_date, end_date=end_date, evidence=False)


def query_macro_evidence(
    *,
    path: Path = DEFAULT_MACRO_EVIDENCE_PATH,
    metric_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Query source-grounded Macro OBSERVATION records."""
    return _query(path, metric_id=metric_id, start_date=start_date, end_date=end_date, evidence=True)
