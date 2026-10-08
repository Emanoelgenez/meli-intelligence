from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd
import pytest

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.market_storytelling import (
    MARKET_PRICE_COLUMNS,
    market_freshness,
    select_latest_market_price,
    select_market_trend,
)


def prices() -> pd.DataFrame:
    rows = [
        ("MELI", date(2024, 1, 2), 1600.0),
        ("MELI", date(2024, 1, 4), 1625.5),
        ("OTHER", date(2024, 1, 5), 99.0),
    ]
    return pd.DataFrame([
        {
            "ticker": ticker,
            "entity": "MercadoLibre, Inc." if ticker == "MELI" else "Other Corp",
            "reference_date": reference_date,
            "close": close,
            "currency": "USD",
            "source": "fixture-market-source",
            "source_url": "https://example.invalid/market.csv",
            "retrieved_at": "2024-01-06T00:00:00Z",
        }
        for ticker, reference_date, close in rows
    ])


def test_market_reader_contract_and_latest_price_keep_source_currency() -> None:
    frame = prices()
    latest = select_latest_market_price(frame)
    assert latest is not None
    assert latest.ticker == "MELI"
    assert latest.entity == "MercadoLibre, Inc."
    assert latest.reference_date == date(2024, 1, 4)
    assert latest.close == 1625.5
    assert latest.currency == "USD"
    assert "US$" in latest.formatted_close
    assert latest.source == "fixture-market-source"
    assert latest.source_url.startswith("https://")
    assert latest.retrieved_at.endswith("Z")
    assert all(column in MARKET_PRICE_COLUMNS for column in latest.__dict__ if column in MARKET_PRICE_COLUMNS)


def test_price_trend_is_chronological_and_preserves_missing_trading_dates() -> None:
    frame = prices().sample(frac=1, random_state=5)
    before = frame.copy(deep=True)
    trend = select_market_trend(frame)
    assert trend.reference_date.tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")]
    assert trend.close.tolist() == [1600.0, 1625.5]
    assert len(trend) == 2  # Jan 3 is not synthesized.
    pd.testing.assert_frame_equal(frame, before)


def test_filters_apply_to_trading_reference_date_and_invalid_range_fails() -> None:
    latest = select_latest_market_price(
        prices(), filters=FilterState(start_date=date(2024, 1, 2), end_date=date(2024, 1, 2))
    )
    assert latest is not None and latest.reference_date == date(2024, 1, 2)
    with pytest.raises(ValueError, match="on or before"):
        select_market_trend(prices(), filters=FilterState(start_date=date(2024, 2, 1), end_date=date(2024, 1, 1)))


def test_missing_empty_and_other_ticker_are_not_zero_fallbacks() -> None:
    assert select_latest_market_price(None) is None
    assert select_latest_market_price(pd.DataFrame(columns=MARKET_PRICE_COLUMNS)) is None
    only_other = prices().loc[lambda frame: frame.ticker == "OTHER"]
    assert select_latest_market_price(only_other) is None
    assert market_freshness(None) is None


def test_duplicate_economic_keys_and_invalid_market_schema_fail_explicitly() -> None:
    frame = prices()
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate market economic key"):
        select_market_trend(duplicate)
    with pytest.raises(ValueError, match="missing required columns"):
        select_market_trend(frame.drop(columns="currency"))


def test_ui_does_not_calculate_returns_or_valuation_or_join_company_facts() -> None:
    root = Path(__file__).resolve().parents[2]
    page = (root / "src/meli_intelligence/ui/pages/market.py").read_text(encoding="utf-8").casefold()
    helper = (root / "src/meli_intelligence/ui/market_storytelling.py").read_text(encoding="utf-8").casefold()
    app = (root / "streamlit_app.py").read_text(encoding="utf-8")
    forbidden_imports = ("meli_intelligence.sources", "meli_intelligence.pipelines", "meli_intelligence.transformations")
    assert not any(item in page for item in forbidden_imports)
    assert not any(item in page for item in ("to_parquet(", ".to_csv(", "write_parquet(", "insert into", "delete from"))
    assert not any(item in helper for item in ("pct_change(", "cumprod(", "rolling(", "market_cap", "ev/ebitda", "pe_ratio"))
    assert "render_valuation(st, health_records, filters=state)" in page
    assert "financial_facts" not in page and "query_financial_facts" not in page
    assert "market.render" in app
    assert "streamlit" not in sys.modules


def test_navigation_and_prior_ui_apis_are_preserved() -> None:
    from meli_intelligence.ui.domain_storytelling import domain_navigation_order
    from meli_intelligence.ui.pages import NAVIGATION_OPTIONS
    from meli_intelligence.ui.pages.executive_overview import availability_by_domain_layer
    from meli_intelligence.ui.macro_storytelling import select_macro_snapshots
    from meli_intelligence.ui.strategy_storytelling import summarize_pestel, summarize_swot
    from meli_intelligence.ui.product_storytelling import select_product_hypotheses
    from meli_intelligence.ui.financial_storytelling import select_financial_snapshots

    expected = (
        "Executive Overview", "Financial", "Commerce", "Fintech", "Macro", "PESTEL", "SWOT",
        "Product Evidence", "Market", "Data Quality & Sources",
    )
    assert NAVIGATION_OPTIONS == expected
    assert domain_navigation_order() == expected
    assert all(callable(function) for function in (
        availability_by_domain_layer, select_macro_snapshots, summarize_pestel,
        summarize_swot, select_product_hypotheses, select_financial_snapshots,
    ))

