"""DuckDB queries for canonical operational KPI Silver facts."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.storage.operational_silver import (
    DEFAULT_OPERATIONAL_SILVER_PATH,
)


def query_operational_kpis(
    parquet_path: Path = DEFAULT_OPERATIONAL_SILVER_PATH,
    *,
    metric_id: str | None = None,
    period_type: str | None = None,
    definition_version: str | None = None,
    min_reference_year: int | None = None,
) -> pd.DataFrame:
    """Query canonical operational facts directly from Parquet."""
    conditions = []
    parameters: list[
        str | int
    ] = []

    if metric_id is not None:
        conditions.append(
            "metric_id = ?"
        )
        parameters.append(
            metric_id
        )

    if period_type is not None:
        conditions.append(
            "period_type = ?"
        )
        parameters.append(
            period_type
        )

    if definition_version is not None:
        conditions.append(
            "definition_version = ?"
        )
        parameters.append(
            definition_version
        )

    if min_reference_year is not None:
        conditions.append(
            "reference_year >= ?"
        )
        parameters.append(
            min_reference_year
        )

    where = (
        " WHERE "
        + " AND ".join(
            conditions
        )
        if conditions
        else ""
    )

    sql = f"""
        SELECT *
        FROM read_parquet(?)
        {where}
        ORDER BY
            period_end,
            metric_id,
            definition_version
    """

    return duckdb.connect(
        database=":memory:"
    ).execute(
        sql,
        [
            str(parquet_path),
            *parameters,
        ],
    ).fetchdf()


def operational_kpis_summary(
    parquet_path: Path = DEFAULT_OPERATIONAL_SILVER_PATH,
) -> pd.DataFrame:
    """Summarize canonical fact coverage by definition."""
    sql = """
        SELECT
            metric_id,
            definition_version,
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
            definition_version,
            period_type
        ORDER BY
            metric_id,
            definition_version,
            period_type
    """

    return duckdb.connect(
        database=":memory:"
    ).execute(
        sql,
        [
            str(parquet_path)
        ],
    ).fetchdf()