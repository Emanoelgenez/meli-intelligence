"""Read-only Financial facts storytelling page."""
from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.financial_storytelling import (
    FINANCIAL_QUESTION,
    financial_freshness,
    financial_metric_label,
    financial_metric_availability,
    financial_period_description,
    select_financial_context,
    select_financial_interpretations,
    select_financial_snapshots,
    select_financial_trend,
)
from meli_intelligence.ui.presentation import format_date

DATASET_IDS = ("financial_facts", "interpretations")


def _load(health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    health_by_id = {item.dataset_id: item for item in health_records}
    frames: dict[str, pd.DataFrame | None] = {}
    degraded, failures = [], []
    for dataset_id in DATASET_IDS:
        item = health_by_id.get(dataset_id)
        if item is None or item.status != "AVAILABLE":
            frames[dataset_id] = None
            degraded.append(f"{dataset_id}: {item.status if item else 'MISSING'}")
            continue
        try:
            date_filters = FilterState(start_date=filters.start_date, end_date=filters.end_date)
            frames[dataset_id] = load_dataset(dataset_id, path=item.path, filters=date_filters)
        except Exception as exc:
            frames[dataset_id] = None
            failures.append(f"{dataset_id}: {type(exc).__name__}")
    return frames, degraded, failures


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    frames, degraded, failures = _load(health_records, state)
    facts = frames.get("financial_facts")
    st.title("Financial")
    st.caption(FINANCIAL_QUESTION)
    st.caption(f"Latest economic period end: {format_date(financial_freshness(facts, filters=state))}")
    if degraded:
        st.warning("Financial data availability is limited: " + "; ".join(degraded) + ". See Data Quality & Sources for details.")
    if failures:
        st.warning("Some datasets could not be read for this view: " + "; ".join(failures) + ".")

    st.subheader("Key reported financial facts")
    snapshots = select_financial_snapshots(facts, filters=state)
    if snapshots:
        columns = st.columns(min(len(snapshots), 4))
        for column, fact in zip(columns, snapshots):
            with column:
                st.metric(fact.display_name, fact.formatted_value)
                st.caption(financial_period_description(fact))
                st.caption(fact.context)
                with st.expander("Reported source and precision"):
                    st.write(f"Unit: {fact.unit or 'not reported'}")
                    st.write(f"Source: {fact.source}")
                    st.write(f"Filing date: {format_date(fact.filing_date)} · Form: {fact.form or 'not reported'}")
                    st.write(f"Accession number: {fact.accession_number or 'not reported'}")
                    st.write(f"Value as loaded: {fact.full_precision_value}")
    else:
        st.info("No allowlisted quarterly Financial facts are available in this period. Missing values are not replaced with zero.")
    missing = financial_metric_availability(facts, filters=state)
    if missing:
        st.caption("Priority measures unavailable for this period: " + ", ".join(missing) + ".")

    st.subheader("Primary trend · reported quarterly revenue")
    trend = select_financial_trend(facts, filters=state)
    if trend.empty:
        st.info("No comparable quarterly revenue series is available for the selected period.")
    else:
        st.caption("Quarterly duration facts, shown at their reported period ends. No periods are filled, resampled or recalculated.")
        st.line_chart(trend, x="period_end", y="value", x_label="Economic period end", y_label="Reported revenue and financial income (USD)")

    interpretations = select_financial_interpretations(frames.get("interpretations"), filters=state)
    st.subheader("Existing Financial interpretations")
    if not interpretations:
        st.info("No persisted Financial interpretation is available for this period.")
    else:
        for item in interpretations:
            st.markdown(f"**Interpretation · {financial_metric_label(item.metric_id)}**")
            st.write(item.claim)
            st.caption(f"{item.source} · {format_date(item.reference_date)} · Evidence ID: {item.evidence_id}")

    with st.expander("Profitability, cash generation and balance-sheet context"):
        context = select_financial_context(facts, filters=state)
        if not context:
            st.info("No allowlisted supporting facts are available for this period.")
        else:
            detail = pd.DataFrame([
                {
                    "Measure": fact.display_name,
                    "Reported value": fact.formatted_value,
                    "Period": financial_period_description(fact),
                    "Filing date": format_date(fact.filing_date),
                    "Source": fact.source,
                }
                for fact in context
            ])
            st.dataframe(detail, width="stretch", hide_index=True)
    with st.expander("Methodology and limits"):
        st.write("This page presents normalized SEC Company Facts only. Period end describes the economic period; filing date and accession number remain filing context.")
        st.write("Quarter, year-to-date, fiscal-year and instant facts are not combined. No financial growth, margins, cash-flow ratios or annual/quarterly conversions are calculated in the UI.")
        st.write("Company fundamentals are separate from market prices and valuation. Financial facts do not establish user behavior, Product outcomes or causality.")
    st.caption("Date filters use economic period_end. Filing dates do not replace economic freshness.")
