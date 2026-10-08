"""Tests for DuckDB operational KPI queries."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.query.operational import (
    query_operational_kpis,
)


def test_query_operational_kpis(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "operational.parquet"
    )

    frame = pd.DataFrame(
        {
            "metric_id": [
                "gmv",
                "fintech_mau",
            ],
            "definition_version": [
                "v2_food_delivery",
                "v2_active_policy_and_current_loan",
            ],
            "period_type": [
                "QUARTER",
                "INSTANT",
            ],
            "period_end": pd.to_datetime(
                [
                    "2026-06-30",
                    "2026-06-30",
                ]
            ),
            "reference_year": [
                2026,
                2026,
            ],
            "value": [
                21_926_000_000.0,
                88_000_000.0,
            ],
        }
    )

    pq.write_table(
        pa.Table.from_pandas(
            frame,
            preserve_index=False,
        ),
        path,
    )

    result = query_operational_kpis(
        path,
        metric_id="gmv",
        period_type="QUARTER",
        min_reference_year=2026,
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["value"]
        == 21_926_000_000.0
    )