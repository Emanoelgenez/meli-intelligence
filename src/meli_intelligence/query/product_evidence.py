"""DuckDB query layer for Product Evidence Gold."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.product.evidence import DISCOVERY_THEMES, PRODUCT_EVIDENCE_TYPES
from meli_intelligence.storage.product_evidence import DEFAULT_PRODUCT_EVIDENCE_PATH


def query_product_evidence(
    *,
    path: str | Path = DEFAULT_PRODUCT_EVIDENCE_PATH,
    product_evidence_type: str | None = None,
    discovery_theme: str | None = None,
    business_domain: str | None = None,
    metric_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source_evidence_id: str | None = None,
    source_pestel_id: str | None = None,
    source_swot_id: str | None = None,
    source_hypothesis_id: str | None = None,
) -> pd.DataFrame:
    if product_evidence_type is not None and product_evidence_type not in PRODUCT_EVIDENCE_TYPES:
        raise ValueError(f"Invalid Product Evidence type: {product_evidence_type}")
    if discovery_theme is not None and discovery_theme not in DISCOVERY_THEMES:
        raise ValueError(f"Invalid Product discovery theme: {discovery_theme}")
    if start_date is not None and not isinstance(start_date, date):
        raise ValueError("start_date must be a date.")
    if end_date is not None and not isinstance(end_date, date):
        raise ValueError("end_date must be a date.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    parquet_path = Path(path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Product Evidence Parquet not found: {parquet_path}")
    conditions = []
    parameters: list[object] = [str(parquet_path)]
    for column, value in (
        ("product_evidence_type", product_evidence_type),
        ("discovery_theme", discovery_theme),
        ("business_domain", business_domain),
    ):
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
            " ORDER BY reference_date,product_evidence_type,discovery_theme,product_evidence_id",
            parameters,
        ).df()
    finally:
        connection.close()
    for column, value in (
        ("source_metric_ids", metric_id),
        ("source_evidence_ids", source_evidence_id),
        ("source_pestel_ids", source_pestel_id),
        ("source_swot_ids", source_swot_id),
        ("source_hypothesis_ids", source_hypothesis_id),
    ):
        if value is not None:
            result = result.loc[result[column].map(lambda encoded: value in json.loads(encoded))]
    return result.reset_index(drop=True)
