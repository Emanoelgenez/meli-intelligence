"""DuckDB analytical queries over Silver financial facts."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.storage.silver import (
    DEFAULT_FINANCIAL_FACTS_PATH,
)


def query_financial_facts(
    *,
    parquet_path: Path = DEFAULT_FINANCIAL_FACTS_PATH,
    metric_id: str | None = None,
    period_type: str | None = None,
    min_reference_year: int | None = None,
) -> pd.DataFrame:
    """Query canonical financial facts directly from Parquet."""
    parquet_path = Path(parquet_path)

    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Silver Parquet not found: {parquet_path}"
        )

    conditions: list[str] = []
    parameters: list[object] = [
        str(parquet_path)
    ]

    if metric_id is not None:
        conditions.append(
            "metric_id = ?"
        )
        parameters.append(metric_id)

    if period_type is not None:
        conditions.append(
            "period_type = ?"
        )
        parameters.append(period_type)

    if min_reference_year is not None:
        conditions.append(
            "reference_year >= ?"
        )
        parameters.append(min_reference_year)

    where_clause = ""

    if conditions:
        where_clause = (
            " WHERE "
            + " AND ".join(conditions)
        )

    sql = (
        "SELECT * "
        "FROM read_parquet(?)"
        + where_clause
        + " ORDER BY "
        "period_end, "
        "metric_id, "
        "period_start NULLS FIRST"
    )

    connection = duckdb.connect(
        database=":memory:"
    )

    try:
        return connection.execute(
            sql,
            parameters,
        ).df()

    finally:
        connection.close()


def financial_facts_summary(
    *,
    parquet_path: Path = DEFAULT_FINANCIAL_FACTS_PATH,
) -> pd.DataFrame:
    """Return a compact dataset-quality summary."""
    parquet_path = Path(parquet_path)

    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Silver Parquet not found: {parquet_path}"
        )

    connection = duckdb.connect(
        database=":memory:"
    )

    try:
        return connection.execute(
            """
            SELECT
                metric_id,
                period_type,
                COUNT(*) AS observations,
                MIN(period_end) AS first_period,
                MAX(period_end) AS latest_period,
                SUM(
                    CASE
                        WHEN has_value_change
                        THEN 1
                        ELSE 0
                    END
                ) AS value_changes
            FROM read_parquet(?)
            GROUP BY
                metric_id,
                period_type
            ORDER BY
                metric_id,
                period_type
            """,
            [str(parquet_path)],
        ).df()

    finally:
        connection.close()