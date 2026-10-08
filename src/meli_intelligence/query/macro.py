"""DuckDB query helpers for macro indicator Silver."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.storage.macro import DEFAULT_MACRO_INDICATORS_PATH


def query_macro_indicators(
    *,
    parquet_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
    metric_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Query macro Silver with optional metric and reference-date bounds."""
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Macro Silver Parquet not found: {parquet_path}")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    conditions = []
    parameters: list[object] = [str(parquet_path)]
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
    connection = duckdb.connect(database=":memory:")
    try:
        return connection.execute(
            "SELECT * FROM read_parquet(?)"
            + where
            + " ORDER BY reference_date, metric_id",
            parameters,
        ).df()
    finally:
        connection.close()
