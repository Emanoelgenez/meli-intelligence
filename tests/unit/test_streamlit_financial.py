from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd
import pytest

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.financial_storytelling import (
    FINANCIAL_CONTEXT,
    FINANCIAL_PRIORITY,
    financial_freshness,
    financial_metric_availability,
    select_financial_context,
    select_financial_interpretations,
    select_financial_snapshots,
    select_financial_trend,
)


def fact(metric: str, value: int, start: str, end: str, *, period_type: str = "QUARTER", unit: str = "USD", filed: str = "2025-05-01") -> dict:
    return {
        "entity_cik": "0001099590",
        "entity_name": "MercadoLibre, Inc.",
        "source": "SEC EDGAR Company Facts API",
        "metric_id": metric,
        "taxonomy": "us-gaap",
        "concept": metric,
        "unit": unit,
        "value": value,
        "period_start": start,
        "period_end": end,
        "reference_year": int(end[:4]),
        "period_type": period_type,
        "period_label": f"{start} to {end}",
        "form": "10-Q",
        "filed_at": filed,
        "accession_number": f"acc-{metric}-{end}",
        "occurrences": 1,
        "has_value_change": False,
        "is_derived": False,
    }


@pytest.fixture
def facts() -> pd.DataFrame:
    return pd.DataFrame([
        fact("net_revenues_financial_income", 100, "2024-01-01", "2024-03-31", filed="2024-05-01"),
        fact("net_revenues_financial_income", 150, "2024-04-01", "2024-06-30", filed="2024-08-01"),
        fact("operating_income", 30, "2024-04-01", "2024-06-30"),
        fact("net_income", 20, "2024-04-01", "2024-06-30"),
        fact("operating_cash_flow", 40, "2024-04-01", "2024-06-30"),
        # Annual/YTD facts are deliberately not substituted for quarterly cards.
        fact("net_revenues_financial_income", 500, "2024-01-01", "2024-12-31", period_type="FY", filed="2025-02-01"),
        fact("cash_and_equivalents", 300, "2024-06-30", "2024-06-30", period_type="INSTANT"),
        fact("total_assets", 900, "2024-06-30", "2024-06-30", period_type="INSTANT"),
    ])


def test_allowlist_uses_real_metric_ids_and_is_deterministic_with_four_card_limit(facts: pd.DataFrame) -> None:
    assert tuple(spec.metric_id for spec in FINANCIAL_PRIORITY) == (
        "net_revenues_financial_income", "operating_income", "net_income", "operating_cash_flow"
    )
    assert len(FINANCIAL_PRIORITY) == 4
    assert tuple(select_financial_snapshots(facts)) == tuple(select_financial_snapshots(facts.sample(frac=1, random_state=4)))


def test_snapshot_uses_quarterly_period_and_preserves_filing_context(facts: pd.DataFrame) -> None:
    revenue = select_financial_snapshots(facts)[0]
    assert revenue.metric_id == "net_revenues_financial_income"
    assert revenue.value == 150
    assert revenue.period_type == "QUARTER"
    assert revenue.period_start == date(2024, 4, 1)
    assert revenue.period_end == date(2024, 6, 30)
    assert revenue.filing_date == date(2024, 8, 1)
    assert revenue.accession_number == "acc-net_revenues_financial_income-2024-06-30"
    assert revenue.unit == "USD" and "US$" in revenue.formatted_value
    assert revenue.full_precision_value == "150 USD"


def test_trend_is_chronological_without_filling_missing_periods(facts: pd.DataFrame) -> None:
    unordered = facts.sample(frac=1, random_state=1)
    before = unordered.copy(deep=True)
    trend = select_financial_trend(unordered)
    assert trend.period_end.tolist() == [pd.Timestamp("2024-03-31"), pd.Timestamp("2024-06-30")]
    assert trend.value.tolist() == [100, 150]
    assert len(trend) == 2
    pd.testing.assert_frame_equal(unordered, before)


def test_date_filters_and_invalid_interval(facts: pd.DataFrame) -> None:
    selected = select_financial_snapshots(
        facts,
        filters=FilterState(business_domain="Financial", start_date=date(2024, 1, 1), end_date=date(2024, 3, 31)),
    )
    assert len(selected) == 1 and selected[0].period_end == date(2024, 3, 31)
    with pytest.raises(ValueError, match="on or before"):
        select_financial_snapshots(facts, filters=FilterState(start_date=date(2024, 8, 1), end_date=date(2024, 1, 1)))


def test_freshness_is_economic_period_end_not_filing_date(facts: pd.DataFrame) -> None:
    assert financial_freshness(facts) == date(2024, 12, 31)
    assert financial_freshness(facts, filters=FilterState(end_date=date(2024, 6, 30))) == date(2024, 6, 30)
    assert financial_freshness(None) is None


def test_context_keeps_instant_balance_facts_separate(facts: pd.DataFrame) -> None:
    context = select_financial_context(facts)
    balances = [item for item in context if item.period_type == "INSTANT"]
    assert {item.metric_id for item in balances} == {"cash_and_equivalents", "total_assets"}
    assert all(item.period_start == item.period_end for item in balances)
    assert len(FINANCIAL_CONTEXT) == 6


def test_missing_facts_are_not_zero_and_availability_is_explicit(facts: pd.DataFrame) -> None:
    frame = facts.loc[facts.metric_id == "net_revenues_financial_income"].copy()
    assert select_financial_snapshots(frame)[0].value != 0
    assert "Operating cash flow" in financial_metric_availability(frame)
    assert select_financial_snapshots(None) == ()
    assert financial_metric_availability(None) == tuple(spec.display_name for spec in FINANCIAL_PRIORITY)


def test_interpretations_are_filtered_to_financial_and_type() -> None:
    frame = pd.DataFrame([
        {"evidence_id": "i1", "evidence_type": "INTERPRETATION", "business_domain": "Financial", "metric_id": "revenue", "source_metric_id": "net_revenues_financial_income", "reference_date": "2024-06-30", "claim": "Persisted claim", "source": "SEC"},
        {"evidence_id": "o1", "evidence_type": "OBSERVATION", "business_domain": "Financial", "metric_id": "revenue", "reference_date": "2024-06-30", "claim": "Observation", "source": "SEC"},
        {"evidence_id": "i2", "evidence_type": "INTERPRETATION", "business_domain": "Macro", "metric_id": "selic", "reference_date": "2024-06-30", "claim": "Other domain", "source": "BCB"},
    ])
    selected = select_financial_interpretations(frame)
    assert len(selected) == 1
    assert selected[0].evidence_id == "i1"
    assert selected[0].claim == "Persisted claim"
    assert select_financial_interpretations(None) == ()


def test_duplicate_economic_key_fails_instead_of_selecting_a_filing() -> None:
    row = fact("net_revenues_financial_income", 100, "2024-01-01", "2024-03-31")
    duplicate = row | {"value": 101, "accession_number": "different-accession"}
    with pytest.raises(ValueError, match="Duplicate financial economic keys"):
        select_financial_snapshots(pd.DataFrame([row, duplicate]))


def test_page_is_thin_read_only_and_excludes_market_and_analytics_calculation() -> None:
    root = Path(__file__).resolve().parents[2]
    page = (root / "src/meli_intelligence/ui/pages/financial.py").read_text(encoding="utf-8").casefold()
    helper = (root / "src/meli_intelligence/ui/financial_storytelling.py").read_text(encoding="utf-8").casefold()
    app = (root / "streamlit_app.py").read_text(encoding="utf-8")
    assert not any(token in page for token in (".sources", ".pipelines", ".transformations", "to_parquet(", ".to_csv(", "write_parquet("))
    assert not any(term in page + helper for term in ("market_cap", "meli34", "ev/ebitda", "stock_return"))
    assert not any(term in helper for term in ("build_financial_analytics", "yoy_growth", "gross_margin", "free_cash_flow"))
    assert "financial.render" in app
    assert "interpretation" in page
    assert "period_end" in helper and "filed_at" in helper
    assert "streamlit" not in sys.modules
