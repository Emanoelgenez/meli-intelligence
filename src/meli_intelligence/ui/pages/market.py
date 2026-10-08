"""Thin, read-only Market price page; does not calculate returns or valuation."""
from __future__ import annotations

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.market_storytelling import (
    market_freshness,
    select_latest_market_price,
    select_market_trend,
)
from meli_intelligence.ui.presentation import format_date, unavailable_message
from meli_intelligence.ui.valuation_storytelling import render as render_valuation
from meli_intelligence.ui.public_demo import public_demo_enabled

DATASET_ID = "market_prices"


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    from meli_intelligence.ui.data import load_dataset

    state = (filters or FilterState()).validate()
    health = next((item for item in health_records if item.dataset_id == DATASET_ID), None)
    frame = None
    status = health.status if health is not None else "MISSING"
    error = None
    if health is not None and health.status == "AVAILABLE":
        try:
            frame = load_dataset(
                DATASET_ID,
                path=health.path,
                filters=FilterState(start_date=state.start_date, end_date=state.end_date),
            )
        except Exception as exc:
            status = "INVALID"
            error = type(exc).__name__

    st.title("Market")
    st.caption("What does the market data say about MELI's price behavior and valuation context, without confusing market movements with business fundamentals?")
    st.caption("Market observations do not establish Product or user behavior.")
    try:
        freshness = market_freshness(frame, filters=state)
    except (ValueError, KeyError, TypeError) as exc:
        status = "INVALID"
        error = type(exc).__name__
        freshness = None
    st.caption(f"Market dataset status: {status} · Latest trading date: {format_date(freshness)}")
    if status != "AVAILABLE":
        st.warning(unavailable_message(
            "MELI market-price data", status,
            reason=health.message if health is not None and public_demo_enabled() else None,
            boundary="No price is substituted or synthesized.",
        ))
        if error:
            st.caption(f"Dataset validation/read detail: {error}. See Data Quality & Sources for diagnosis.")
    else:
        try:
            latest = select_latest_market_price(frame, filters=state)
            if latest is not None:
                st.subheader("Latest persisted market price")
                st.metric(f"{latest.ticker} closing price", latest.formatted_close)
                st.caption(f"{latest.entity} · Trading date: {format_date(latest.reference_date)} · Currency: {latest.currency}")
                with st.expander("Source provenance and retrieval context"):
                    st.write(f"Source: {latest.source}")
                    st.write(f"Source URL: {latest.source_url}")
                    st.write(f"Retrieved at: {latest.retrieved_at} (technical timestamp)")
                    st.write(f"Close at full precision: {latest.close!r} {latest.currency}")
            trend = select_market_trend(frame, filters=state)
            st.subheader("Persisted closing-price trend")
            if trend.empty:
                st.info("No MELI trading observations are available in the selected date range.")
            else:
                st.caption("Only persisted trading dates are shown. No missing trading days are filled, and no resampling is applied.")
                st.line_chart(trend, x="reference_date", y="close", x_label="Trading date", y_label=f"MELI close ({latest.currency if latest else 'source currency'})")
        except (ValueError, KeyError, TypeError) as exc:
            st.warning("Market price data is INVALID for this view; no values were presented.")
            st.caption(f"Validation detail: {type(exc).__name__}. See Data Quality & Sources for diagnosis.")

    render_valuation(st, health_records, filters=state)
    with st.expander("Market-data and valuation limits"):
        st.write("Market prices are a separate layer from company financial and operational fundamentals. Valuation consumes persisted Gold through backend analytics; the page does not join raw prices to Company facts.")
        st.write("MELI34, if added in a future market dataset, is a Brazilian market instrument/BDR. It does not have separate company revenue, profit, GMV, TPV, MAU or balance-sheet fundamentals, and no parity is inferred here.")
        st.write("Valuation values and eligibility come from backend analytics. This page performs no financial calculations and produces no causal claims or investment advice.")
        st.write("Valuation availability depends on authoritative persisted inputs and compatible financial periods. Unavailable observations never fall back to an older numeric valuation.")
    st.caption("Date filters apply to persisted trading reference dates. Retrieval time is technical provenance, not market freshness.")
