"""Tests for fundamental financial analytics."""

from __future__ import annotations

import pandas as pd
import pytest

from meli_intelligence.analytics.financial import (
    build_financial_analytics,
    calculate_free_cash_flow,
    calculate_margin,
    calculate_yoy_growth,
)


def _row(
    metric_id: str,
    *,
    start: str,
    end: str,
    period_type: str,
    period_label: str,
    value: int,
) -> dict:
    return {
        "metric_id": metric_id,
        "period_start": pd.Timestamp(start),
        "period_end": pd.Timestamp(end),
        "reference_year": int(end[:4]),
        "period_type": period_type,
        "period_label": period_label,
        "value": value,
        "unit": "USD",
    }


def test_margin_uses_exact_matching_period() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "net_revenues_financial_income",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=10_000,
            ),
            _row(
                "gross_profit",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=4_000,
            ),
        ]
    )

    result = calculate_margin(
        facts,
        "gross_profit",
        "gross_margin",
    )

    assert len(result) == 1
    assert result.iloc[0]["value"] == pytest.approx(40.0)
    assert result.iloc[0]["unit"] == "percent"


def test_yoy_growth_compares_same_period_label() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "net_revenues_financial_income",
                start="2025-04-01",
                end="2025-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=100,
            ),
            _row(
                "net_revenues_financial_income",
                start="2026-04-01",
                end="2026-06-30",
                period_type="QUARTER",
                period_label="Q2",
                value=125,
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "net_revenues_financial_income",
    )

    assert len(result) == 1
    assert result.iloc[0]["value"] == pytest.approx(25.0)


def test_yoy_growth_requires_matching_calendar_period() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "net_revenues_financial_income",
                start="2025-07-01",
                end="2025-09-30",
                period_type="QUARTER",
                period_label="Q3",
                value=100,
            ),
            _row(
                "net_revenues_financial_income",
                start="2025-07-02",
                end="2025-09-30",
                period_type="QUARTER",
                period_label="Q3",
                value=900,
            ),
            _row(
                "net_revenues_financial_income",
                start="2026-07-01",
                end="2026-09-30",
                period_type="QUARTER",
                period_label="Q3",
                value=120,
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "net_revenues_financial_income",
    )

    assert len(result) == 1
    assert result.iloc[0]["value"] == pytest.approx(20.0)


def test_yoy_growth_skips_nonpositive_base() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "net_income",
                start="2025-01-01",
                end="2025-03-31",
                period_type="QUARTER",
                period_label="Q1",
                value=-10,
            ),
            _row(
                "net_income",
                start="2026-01-01",
                end="2026-03-31",
                period_type="QUARTER",
                period_label="Q1",
                value=20,
            ),
        ]
    )

    result = calculate_yoy_growth(
        facts,
        "net_income",
    )

    assert result.empty


def test_free_cash_flow_uses_productive_assets_capex() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "operating_cash_flow",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=5_737,
            ),
            _row(
                "capex_productive_assets",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=712,
            ),
        ]
    )

    result = calculate_free_cash_flow(
        facts
    )

    assert len(result) == 1
    assert result.iloc[0]["value"] == 5_025
    assert result.iloc[0]["unit"] == "USD"


def test_productive_assets_capex_supports_annual_history() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "operating_cash_flow",
                start="2022-01-01",
                end="2022-12-31",
                period_type="FY",
                period_label="FY",
                value=2_940,
            ),
            _row(
                "capex_productive_assets",
                start="2022-01-01",
                end="2022-12-31",
                period_type="FY",
                period_label="FY",
                value=455,
            ),
            _row(
                "capex_ppe_legacy",
                start="2022-01-01",
                end="2022-12-31",
                period_type="FY",
                period_label="FY",
                value=454,
            ),
        ]
    )

    result = calculate_free_cash_flow(
        facts
    )

    assert len(result) == 1
    assert result.iloc[0]["value"] == 2_485


def test_legacy_capex_is_not_automatically_blended() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "operating_cash_flow",
                start="2023-01-01",
                end="2023-12-31",
                period_type="FY",
                period_label="FY",
                value=1_000,
            ),
            _row(
                "capex_ppe_legacy",
                start="2023-01-01",
                end="2023-12-31",
                period_type="FY",
                period_label="FY",
                value=100,
            ),
        ]
    )

    result = calculate_free_cash_flow(
        facts
    )

    assert result.empty


def test_build_financial_analytics() -> None:
    facts = pd.DataFrame(
        [
            _row(
                "net_revenues_financial_income",
                start="2025-01-01",
                end="2025-06-30",
                period_type="YTD",
                period_label="H1",
                value=10_000,
            ),
            _row(
                "net_revenues_financial_income",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=12_000,
            ),
            _row(
                "gross_profit",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=5_000,
            ),
            _row(
                "operating_income",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=1_500,
            ),
            _row(
                "net_income",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=900,
            ),
            _row(
                "operating_cash_flow",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=3_000,
            ),
            _row(
                "capex_productive_assets",
                start="2026-01-01",
                end="2026-06-30",
                period_type="YTD",
                period_label="H1",
                value=500,
            ),
        ]
    )

    result = build_financial_analytics(
        facts
    )

    metrics = set(
        result["metric_id"]
    )

    assert "gross_margin" in metrics
    assert "operating_margin" in metrics
    assert "net_margin" in metrics
    assert "operating_cash_flow_margin" in metrics
    assert "free_cash_flow" in metrics
    assert "free_cash_flow_margin" in metrics
    assert "capex" in metrics
    assert (
        "net_revenues_financial_income_yoy_growth"
        in metrics
    )