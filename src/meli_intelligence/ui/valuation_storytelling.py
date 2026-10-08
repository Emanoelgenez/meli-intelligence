"""Read-only valuation presentation; all numerical eligibility belongs to analytics."""
from __future__ import annotations

import pandas as pd

from meli_intelligence.analytics.valuation import (
    STATUS_AVAILABLE,
    ValuationSnapshot,
    build_valuation_snapshot,
)
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import format_date, format_metric, unavailable_message


def valuation_view(
    gold: pd.DataFrame | None,
    financial_facts: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
) -> ValuationSnapshot | None:
    """Use the latest persisted MELI date in the view, including unavailable rows.

    Date filters bound Gold observations only. Financial eligibility remains the
    backend's filing-safe as-of selection, independent of the chart start date.
    """
    state = (filters or FilterState()).validate()
    if gold is None or gold.empty:
        return None
    rows = gold.loc[gold.ticker.eq("MELI")]
    dates = pd.to_datetime(rows.reference_date, errors="raise").dt.date
    if dates.isna().any():
        raise ValueError("Gold reference dates are required.")
    if state.start_date:
        dates = dates.loc[dates >= state.start_date]
    if state.end_date:
        dates = dates.loc[dates <= state.end_date]
    if dates.empty:
        return None
    return build_valuation_snapshot(
        gold, financial_facts, valuation_reference_date=max(dates),
    )


def render(st, health_records, *, filters: FilterState | None = None) -> None:
    """Render a compact section using catalog readers and backend results only."""
    from meli_intelligence.ui.data import load_dataset

    st.subheader("Valuation context")
    st.caption("Market-based indicators from persisted Market Cap Gold and authoritative Company filings. Availability is not an assessment of investment attractiveness.")
    st.caption("P/S and P/Operating Cash Flow require valid TTM denominators; quarterly facts are not annualized. P/E is outside the current scope.")
    records = {item.dataset_id: item for item in health_records}
    frames = {}
    for dataset_id, label in (("market_capitalization", "Market Cap Gold"), ("financial_facts", "Company financial facts")):
        record = records.get(dataset_id)
        status = record.status if record else "MISSING"
        frame = None
        if status == "AVAILABLE":
            try:
                # Do not prefilter financial periods: analytics owns eligibility.
                frame = load_dataset(dataset_id, path=record.path)
                if frame.empty:
                    status = "EMPTY"
            except FileNotFoundError:
                status = "MISSING"
            except Exception:
                status = "INVALID"
        frames[dataset_id] = frame
        st.caption(f"{label}: {status}")
        if status != "AVAILABLE":
            st.info(unavailable_message(
                label, status, boundary="Missing inputs are not replaced with zero or estimated.",
            ))
    try:
        snapshot = valuation_view(frames["market_capitalization"], frames["financial_facts"], filters=filters)
    except (ValueError, TypeError, KeyError, AttributeError):
        st.warning("Valuation inputs are INVALID for this view. No numeric valuation is presented. See Data Quality & Sources.")
        return
    if snapshot is None:
        st.info("Valuation unavailable — no eligible persisted MELI Market Cap Gold observation in this date range.")
        st.caption("Valuation reference date: Unavailable")
        st.info("Price to book: Unavailable — an eligible market capitalization is required.")
        st.info("Price to sales: Unavailable — eligible market capitalization and valid TTM denominators are required.")
        st.info("Price to operating cash flow: Unavailable — eligible market capitalization and valid TTM denominators are required.")
        return

    cap = snapshot.market_cap
    st.caption(f"Valuation reference date: {format_date(snapshot.valuation_reference_date)}")
    if cap.status == STATUS_AVAILABLE:
        st.metric("Market capitalization", format_metric(cap.value, cap.currency))
    else:
        st.info(f"Market capitalization: Unavailable — {cap.reason}")
        st.caption(f"Valuation availability state: {cap.status}")
    for metric in sorted(snapshot.metrics, key=lambda item: item.metric_id != "price_to_book"):
        if metric.status == STATUS_AVAILABLE:
            st.metric(metric.label, f"{metric.value:.2f}x")
        else:
            st.info(f"{metric.label}: Unavailable — {metric.reason}")
    with st.expander("Valuation sources and technical details"):
        details = {
            "Market Cap Gold reference date": format_date(cap.reference_date),
            "Original Gold status": cap.gold_status,
            "Market source": cap.market_source,
            "Shares reference date": format_date(cap.shares_reference_date),
            "Shares filing date": format_date(cap.shares_filed_at),
            "SEC shares accession": cap.shares_accession_number,
            "Methodology version": cap.methodology_version,
            "Market-cap source metric IDs": ", ".join(cap.source_metric_ids),
        }
        for label, value in details.items():
            st.write(f"{label}: {value or 'Not available'}")
        if cap.value is not None:
            st.write(f"Stored market capitalization at full precision: {cap.value!r} {cap.currency}")
        for metric in snapshot.metrics:
            st.write(f"{metric.label} · {metric.status}")
            st.write(f"Source metric IDs: {', '.join(metric.source_metric_ids) or 'Not available'}")
            st.write(f"Source accessions: {', '.join(metric.source_accession_numbers) or 'Not available'}")
        st.caption("Financial denominator period and filing dates are not exposed by the snapshot contract; its source accessions identify the selected filings. Eligibility is checked by backend analytics.")
