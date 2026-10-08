"""DuckDB read layer for SWOT Parquet classifications."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.storage.swot import DEFAULT_SWOT_PATH
from meli_intelligence.strategy.swot import SWOT_CATEGORIES


def query_swot(
    *,
    path: str | Path = DEFAULT_SWOT_PATH,
    swot_category: str | None = None,
    business_domain: str | None = None,
    metric_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source_evidence_id: str | None = None,
    source_pestel_id: str | None = None,
) -> pd.DataFrame:
    if swot_category is not None and swot_category not in SWOT_CATEGORIES:
        raise ValueError(f"Invalid SWOT category: {swot_category}")
    parquet_path = Path(path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"SWOT Parquet not found: {parquet_path}")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    conditions = []
    parameters: list[object] = [str(parquet_path)]
    for column, value in (("swot_category", swot_category), ("business_domain", business_domain)):
        if value is not None:
            conditions.append(f"{column} = ?")
            parameters.append(value)
    if start_date is not None:
        conditions.append("reference_date >= ?")
        parameters.append(start_date)
    if end_date is not None:
        conditions.append("reference_date <= ?")
        parameters.append(end_date)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    connection = duckdb.connect(":memory:")
    try:
        result = connection.execute(
            "SELECT * FROM read_parquet(?)" + where +
            " ORDER BY reference_date,swot_category,business_domain,swot_id",
            parameters,
        ).df()
    finally:
        connection.close()
    if metric_id is not None:
        result = result.loc[result.source_metric_ids.map(lambda encoded: metric_id in json.loads(encoded))]
    if source_evidence_id is not None:
        result = result.loc[result.source_evidence_ids.map(lambda encoded: source_evidence_id in json.loads(encoded))]
    if source_pestel_id is not None:
        result = result.loc[result.source_pestel_ids.map(lambda encoded: source_pestel_id in json.loads(encoded))]
    return result.reset_index(drop=True)
