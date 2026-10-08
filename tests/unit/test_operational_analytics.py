"""Tests for operational KPI analytics."""

from __future__ import annotations

import pandas as pd
import pytest

from meli_intelligence.analytics.operational import (
    calculate_acquiring_tpv_share,
    calculate_gmv_per_buyer,
    calculate_nimal_yoy_change,
    calculate_yoy_growth,
)


def _row(
    metric_id: str,
    *,
    start: str | None,
    end: str,
    period_type: str,
    period_label: str,
    value: float,
    definition: str,
) -> dict:
    return {
        "metric_id": metric_id,
        "period_start": (
            pd.Timestamp(start)
            if start is not None
            else pd.NaT
        ),
        "period_end": pd.Timestamp(
            end
        ),
        "reference_year": int(
            end[:4]
        ),
        "period_type": period_type,
        "period_label": period_label,
        "value": value,
        "unit": "USD",
        "definition_version": (
            definition
        ),
    }


def test_yoy_requires_same_definition_family() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "gmv",
                start="2024-04-01",
                end="2024-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=100,
                definition=(
                    "v1_marketplace_only"
                ),
            ),
            _row(
                "gmv",
                start="2025-04-01",
                end="2025-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=130,
                definition=(
                    "v2_food_delivery"
                ),
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "gmv",
    )

    assert result.empty


def test_yoy_growth_same_definition() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "gmv",
                start="2025-04-01",
                end="2025-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=100,
                definition=(
                    "v2_food_delivery"
                ),
            ),
            _row(
                "gmv",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=125,
                definition=(
                    "v2_food_delivery"
                ),
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "gmv",
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["value"]
        == pytest.approx(25.0)
    )


def test_tpv_recast_definition_is_comparable() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "tpv",
                start="2023-10-01",
                end="2023-12-31",
                period_type="QUARTER",
                period_label="Q4",
                value=100,
                definition=(
                    "v2_recast_excludes_p2p"
                ),
            ),
            _row(
                "tpv",
                start="2024-10-01",
                end="2024-12-31",
                period_type="QUARTER",
                period_label="Q4",
                value=120,
                definition=(
                    "v2_excludes_p2p"
                ),
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "tpv",
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["value"]
        == pytest.approx(20.0)
    )


def test_transition_ytd_is_not_used_for_yoy() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "unique_active_buyers",
                start="2025-01-01",
                end="2025-06-30",
                period_type="YTD",
                period_label="H1",
                value=90,
                definition=(
                    "v2_food_delivery_transition_2025"
                ),
            ),
            _row(
                "unique_active_buyers",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=117,
                definition=(
                    "v2_food_delivery"
                ),
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "unique_active_buyers",
    )

    assert result.empty


def test_nimal_uses_percentage_point_change() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "nimal",
                start="2025-04-01",
                end="2025-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=23.0,
                definition="v1",
            ),
            _row(
                "nimal",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=20.7,
                definition="v1",
            ),
        ]
    )

    result = calculate_nimal_yoy_change(
        facts
    )

    assert len(result) == 1
    assert (
        result.iloc[0]["value"]
        == pytest.approx(-2.3)
    )

    assert (
        result.iloc[0]["unit"]
        == "percentage_points"
    )


def test_gmv_per_buyer_exact_period() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "gmv",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=21_926_000_000,
                definition=(
                    "v2_food_delivery"
                ),
            ),
            {
                **_row(
                    "unique_active_buyers",
                    start="2026-04-01",
                    end="2026-06-30",
                    period_type="QUARTER",
                    period_label="Q2",
                    value=89_000_000,
                    definition=(
                        "v2_food_delivery"
                    ),
                ),
                "unit": "users",
            },
        ]
    )

    result = calculate_gmv_per_buyer(
        facts
    )

    assert len(result) == 1

    assert (
        result.iloc[0]["value"]
        == pytest.approx(
            246.35955056
        )
    )


def test_acquiring_tpv_share() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "acquiring_tpv",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=64_079,
                definition="v1",
            ),
            _row(
                "tpv",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=100_952,
                definition=(
                    "v2_excludes_p2p"
                ),
            ),
        ]
    )

    result = calculate_acquiring_tpv_share(
        facts
    )

    assert len(result) == 1

    assert (
        result.iloc[0]["value"]
        == pytest.approx(
            63.47472066
        )
    )