"""Executive overview renderer; presentation only, with no business calculations."""
from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.data import load_dataset
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import (
    degraded_state_message,
    executive_summary,
    format_date,
    product_evidence_counts,
    select_executive_signals,
    select_latest_interpretations,
)
from meli_intelligence.ui.storytelling import (
    CENTRAL_QUESTION,
    EXECUTIVE_CONTEXT,
    availability_frame,
    count_strategy_records,
)
from meli_intelligence.ui.presentation import format_status

_OVERVIEW_DATASETS = frozenset({
    "financial_facts", "operational_kpis", "macro_indicators", "interpretations",
    "pestel", "swot", "product_evidence",
})


def availability_by_domain_layer(health_records, catalog) -> pd.DataFrame:
    """Keep the Sprint 5A dataframe contract while delegating aggregation."""
    frame = availability_frame(health_records, catalog)
    if frame.empty:
        return pd.DataFrame(columns=["business_domain", "layer", "datasets", "available"])

    status_codes = {
        format_status("AVAILABLE"): "AVAILABLE",
        format_status("MISSING"): "MISSING",
        format_status("EMPTY"): "EMPTY",
        format_status("INVALID"): "INVALID",
    }
    return (
        frame.assign(status=frame["status"].map(status_codes))
        .rename(columns={"dataset_count": "datasets"})
        .loc[:, ["business_domain", "layer", "status", "datasets"]]
        .sort_values(["business_domain", "layer", "status"], kind="mergesort")
        .reset_index(drop=True)
    )


def _available_frames(health_records, filters: FilterState) -> tuple[dict, list[str]]:
    frames = {}
    errors = []
    for health in health_records:
        if health.status != "AVAILABLE" or health.dataset_id not in _OVERVIEW_DATASETS:
            continue
        try:
            frames[health.dataset_id] = load_dataset(
                health.dataset_id, path=health.path, filters=filters
            )
        except Exception as exc:
            errors.append(f"{health.dataset_id}: {type(exc).__name__}")
    return frames, errors


def render(st, health_records, catalog, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    st.title("MELI Intelligence")
    st.caption(EXECUTIVE_CONTEXT)
    st.markdown(f"**Executive question:** {CENTRAL_QUESTION}")

    summary = executive_summary(health_records)
    top = st.columns(2)
    top[0].markdown(f"**Datasets available**  \n{summary.available_count} / {summary.dataset_count}")
    top[1].markdown(f"**Latest data reference**  \n{format_date(summary.latest_reference_date)}")

    message = degraded_state_message(health_records)
    if message:
        st.warning(message)
    frames, read_errors = _available_frames(health_records, state)
    if read_errors:
        st.warning("Some readable datasets could not be loaded for display: " + ", ".join(read_errors))

    st.subheader("Key evidence")
    signals = select_executive_signals(frames, filters=state)
    if signals:
        columns = st.columns(min(len(signals), 4))
        for column, signal in zip(columns, signals):
            with column:
                st.markdown(f"**{signal.business_domain}**")
                st.metric(signal.display_name, signal.formatted_value)
                st.caption(f"{signal.period_label} · Reference date: {format_date(signal.reference_date)}")
                st.caption(signal.context)
                with st.expander("Source and reported precision"):
                    st.write(f"Source: {signal.source}")
                    st.write(f"Metric: {signal.metric_id}")
                    st.write(f"Value as loaded: {signal.full_precision_value}")
        represented = {signal.business_domain for signal in signals}
        missing_domains = [domain for domain in ("Financial", "Commerce", "Fintech", "Macro") if domain not in represented]
        if missing_domains:
            st.caption("No key signal available for: " + ", ".join(missing_domains) + ".")
    else:
        st.info("No key evidence is available for the selected filters. No values are substituted or set to zero.")

    with st.expander("Availability by business area and data layer"):
        st.dataframe(availability_frame(health_records, catalog), width="stretch", hide_index=True)

    st.subheader("Existing interpretations")
    interpretations = select_latest_interpretations(frames.get("interpretations"), filters=state)
    if not interpretations:
        st.info("No existing interpretations are available for the selected period.")
    for item in interpretations:
        st.markdown(f"**Interpretation · {item.metric_id}**")
        st.write(item.claim)
        st.caption(f"{item.source} · {format_date(item.reference_date)} · Evidence ID: {item.evidence_id}")

    with st.expander("Strategy and discovery availability"):
        pestel = frames.get("pestel")
        swot = frames.get("swot")
        product = frames.get("product_evidence")
        pestel_count = count_strategy_records(pestel, "pestel_id") if pestel is not None else None
        swot_count = count_strategy_records(swot, "swot_id") if swot is not None else None
        product_counts = product_evidence_counts(product) if product is not None else None
        st.write(f"PESTEL evidence classifications in available data: {pestel_count if pestel_count is not None else 'Unavailable'}")
        st.write(f"SWOT evidence classifications in available data: {swot_count if swot_count is not None else 'Unavailable'}")
        st.write(f"Discovery hypotheses in available data: {product_counts['hypotheses'] if product_counts is not None else 'Unavailable'}")
        st.write(f"Discovery questions in available data: {product_counts['questions'] if product_counts is not None else 'Unavailable'}")
        st.caption("Hypotheses and questions are investigative material, not business recommendations.")

    st.subheader("Next exploration")
    st.write("Use **Data Quality & Sources** to inspect availability, freshness, and source lineage.")
    st.caption(
        "Freshness is reported from each dataset's latest reference date. "
        "Key evidence is selected from existing reported facts; this page does not calculate new analytics."
    )
