"""Regression coverage for economic periods in the three company dashboards."""

from datetime import date

import pandas as pd
import pytest

from meli_intelligence.analytics.extended_operational import calculate_extended_yoy
from meli_intelligence.analytics.financial import calculate_yoy_growth as financial_yoy
from meli_intelligence.analytics.operational import (
    calculate_yoy_growth as operational_yoy,
)
from meli_intelligence.ui.domain_storytelling import (
    domain_metric_availability,
    select_domain_snapshots,
    select_domain_trend,
)
from meli_intelligence.ui.financial_storytelling import (
    select_financial_context,
    select_financial_trend,
)
from meli_intelligence.ui.temporal_charts import quarterly_chart_spec


def row(metric, end, value=100, period_type="QUARTER", **extra):
    end = pd.Timestamp(end)
    return {
        "metric_id": metric,
        "period_start": end.to_period("Q").start_time,
        "period_end": end,
        "reference_year": end.year,
        "period_type": period_type,
        "period_label": f"Q{end.quarter} {end.year}",
        "value": value,
        "unit": "USD",
        "definition_version": "v1",
        "scope": "total",
        "value_qualifier": "exact",
        **extra,
    }


@pytest.mark.parametrize("domain,metric", [("Commerce", "gmv"), ("Fintech", "tpv")])
def test_flow_series_and_cards_reject_cumulative_and_instant(domain, metric):
    frame = pd.DataFrame(
        [
            row(metric, "2025-03-31", 10),
            row(metric, "2025-09-30", 30),
            *[
                row(metric, "2025-12-31", 999, kind)
                for kind in ("YTD", "FY", "INSTANT")
            ],
        ]
    )
    before = frame.copy(deep=True)
    frames = {"operational_kpis": frame}
    trend = select_domain_trend(frames, domain)
    assert trend.value.tolist() == [10, 30]
    assert trend.reference_date.tolist() == [date(2025, 3, 31), date(2025, 9, 30)]
    assert select_domain_snapshots(frames, domain)[0].value == 30
    pd.testing.assert_frame_equal(frame, before)
    assert select_domain_trend({"operational_kpis": frame.iloc[2:]}, domain).empty
    assert domain_metric_availability({"operational_kpis": frame.iloc[2:]}, domain)


@pytest.mark.parametrize(
    "metric", ["fintech_mau", "aum", "credit_portfolio", "npl_15_90_total"]
)
def test_position_metrics_only_select_instant_observations(metric):
    dataset = (
        "operational_kpis" if metric == "fintech_mau" else "extended_operational_kpis"
    )
    frame = pd.DataFrame(
        [
            row(metric, "2025-03-31", 10, "INSTANT", period_start=pd.NaT),
            row(metric, "2025-06-30", 900, "QUARTER"),
            row(metric, "2025-12-31", 999, "FY"),
        ]
    )
    frames = {dataset: frame}
    assert (
        select_domain_snapshots(frames, "Fintech", metric_ids=(metric,))[0].value == 10
    )
    trend = select_domain_trend(frames, "Fintech", metric_id=metric)
    assert trend.value.tolist() == [10]


def test_financial_flow_and_balance_keep_distinct_granularities():
    metric = "net_revenues_financial_income"
    frame = pd.DataFrame(
        [
            row(metric, "2024-03-31", 10),
            row(metric, "2025-09-30", 30),
            *[
                row(metric, "2025-12-31", 999, kind)
                for kind in ("YTD", "FY", "INSTANT")
            ],
            row("cash_and_equivalents", "2025-03-31", 50, "INSTANT"),
            row("cash_and_equivalents", "2025-12-31", 999, "QUARTER"),
        ]
    )
    assert select_financial_trend(frame).value.tolist() == [10, 30]
    assert select_financial_context(frame)[0].value == 50


@pytest.mark.parametrize(
    "calculate,metric,kind",
    [
        (financial_yoy, "net_revenues_financial_income", "QUARTER"),
        (operational_yoy, "gmv", "QUARTER"),
        (operational_yoy, "tpv", "QUARTER"),
        (calculate_extended_yoy, "aum", "INSTANT"),
    ],
)
def test_yoy_matches_dates_not_labels_or_row_offsets(calculate, metric, kind):
    frame = pd.DataFrame(
        [
            row(metric, "2023-06-30", 10, kind),
            row(metric, "2024-03-31", 90, kind),
            row(metric, "2024-06-30", 100, kind),
            row(metric, "2025-06-30", 125, kind),
        ]
    )
    result = calculate(frame, metric)
    latest = result.loc[result.period_end.eq(pd.Timestamp("2025-06-30"))]
    assert latest.value.tolist() == pytest.approx([25])
    # Previous row / same quarter two years ago must never replace missing YoY.
    assert calculate(frame.iloc[[0, 1, 3]], metric).empty
    frame.loc[2, "period_type"] = "YTD"
    assert calculate(frame.iloc[2:], metric).empty


@pytest.mark.parametrize(
    "calculate,metric",
    [
        (financial_yoy, "net_revenues_financial_income"),
        (operational_yoy, "gmv"),
    ],
)
def test_yoy_uses_economic_year_and_same_unit(calculate, metric):
    frame = pd.DataFrame(
        [
            row(metric, "2024-06-30", 100, reference_year=2000),
            row(metric, "2025-06-30", 125, reference_year=2000),
        ]
    )
    assert calculate(frame, metric).value.tolist() == pytest.approx([25])
    frame.loc[0, "unit"] = "BRL"
    assert calculate(frame, metric).empty


def test_chart_ticks_are_observed_dates_and_real_quarters_across_years():
    frame = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2024-12-31", "2025-06-30"]),
            "value": [10, 20],
        }
    )
    before = frame.copy(deep=True)
    spec = quarterly_chart_spec(frame, "period_end", "Revenue")
    axis = spec["encoding"]["x"]["axis"]
    assert axis["values"] == ["2024-12-31T00:00:00", "2025-06-30T00:00:00"]
    assert axis["labelExpr"] == (
        "utcquarter(datum.value) + 'º tri. ' + "
        "utcyear(datum.value)"
    )
    assert axis["labelOverlap"] == "greedy"
    assert axis["labelAngle"] == -45
    assert axis["labelAlign"] == "right"
    assert axis["labelFontSize"] == 12
    assert axis["labelColor"] == "#344454"
    assert spec["encoding"]["x"]["type"] == "temporal"
    assert "transform" not in spec
    pd.testing.assert_frame_equal(frame, before)


def test_quarter_axis_keeps_economic_date_in_utc_and_formats_currency_in_pt_br():
    frame = pd.DataFrame(
        {
            "period_end": pd.to_datetime(["2025-03-31", "2025-09-30"]),
            "value": [1_250_000_000, 2_500_000_000],
        }
    )
    spec = quarterly_chart_spec(frame, "period_end", "Receita", unit="USD")
    axis = spec["encoding"]["x"]["axis"]
    y_axis = spec["encoding"]["y"]["axis"]
    assert axis["values"] == ["2025-03-31T00:00:00", "2025-09-30T00:00:00"]
    assert "US$ " in y_axis["labelExpr"]
    assert "' bi'" in y_axis["labelExpr"] and "' mi'" in y_axis["labelExpr"]
    assert "replace(format" in y_axis["labelExpr"]