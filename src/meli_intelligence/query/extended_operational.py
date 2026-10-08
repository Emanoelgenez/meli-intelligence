"""DuckDB queries for extended KPIs and evidence facts."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.storage.extended_operational import (
    EVIDENCE_PATH,
    EXTENDED_KPI_PATH,
)


def query_extended_kpis(
    path: Path = EXTENDED_KPI_PATH,
    *,
    metric_id: str | None = None,
) -> pd.DataFrame:
    conditions = []
    parameters: list[str] = [
        str(path)
    ]

    if metric_id is not None:
        conditions.append(
            "metric_id = ?"
        )
        parameters.append(
            metric_id
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
        ORDER BY period_end, metric_id
    """

    return duckdb.connect(
        database=":memory:"
    ).execute(
        sql,
        parameters,
    ).fetchdf()


def query_evidence(
    path: Path = EVIDENCE_PATH,
    *,
    evidence_type: str | None = None,
) -> pd.DataFrame:
    conditions = []
    parameters: list[str] = [
        str(path)
    ]

    if evidence_type is not None:
        conditions.append(
            "evidence_type = ?"
        )
        parameters.append(
            evidence_type
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
        ORDER BY reference_period, evidence_type, evidence_id
    """

    return duckdb.connect(
        database=":memory:"
    ).execute(
        sql,
        parameters,
    ).fetchdf()