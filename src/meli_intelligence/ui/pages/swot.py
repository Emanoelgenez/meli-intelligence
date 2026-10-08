"""Persisted SWOT classification page with explicit internal/external scope."""
from __future__ import annotations

import json

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import format_date
from meli_intelligence.ui.strategy_storytelling import SWOT_DISPLAY_LABELS, SWOT_ORDER, select_swot_items, summarize_swot


def _load(health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    item = next((row for row in health_records if row.dataset_id == "swot"), None)
    if item is None or item.status != "AVAILABLE":
        return None, None if item is None else item.status, None
    try:
        return load_dataset("swot", path=item.path, filters=filters), "AVAILABLE", None
    except Exception as exc:
        return None, "INVALID", type(exc).__name__


def _list(value) -> list[str]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return list(map(str, decoded)) if isinstance(decoded, list) else [str(decoded)]
    return list(map(str, value))


def _render_item(st, row) -> None:
    st.write(str(row.claim))
    st.caption(f"{row.business_domain} · {row.scope} · {row.source} · {format_date(row.reference_date)}")
    st.write(str(row.assessment))
    with st.expander("Classification rationale and lineage"):
        st.write(str(row.classification_rationale))
        st.write("Source Evidence IDs: " + ", ".join(_list(row.source_evidence_ids)))
        st.write("Source Evidence types: " + ", ".join(_list(row.source_evidence_types)))
        st.write("Source metric IDs: " + ", ".join(_list(row.source_metric_ids)))
        pestel_ids = _list(row.source_pestel_ids)
        if pestel_ids:
            st.write("Source PESTEL IDs: " + ", ".join(pestel_ids))
            st.write("Source PESTEL dimensions: " + ", ".join(_list(row.source_pestel_dimensions)))
        st.write(f"Definition context: {row.definition_context}")


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date)
    frame, status, error = _load(health_records, date_filters)
    st.title("SWOT")
    st.caption("Which evidence-backed internal and external factors are currently classified as strengths, weaknesses, opportunities or threats?")
    if status != "AVAILABLE":
        st.warning(f"SWOT dataset status: {status or 'MISSING'}. No classifications are fabricated.")
        if error:
            st.caption(f"Read diagnostic: {error}")
        return
    try:
        summary = summarize_swot(frame, filters=date_filters)
    except ValueError as exc:
        st.error(f"SWOT data could not be presented: {exc}")
        return
    st.caption(f"Latest reference date: {format_date(summary.latest_reference_date)}")
    if not summary.available:
        st.info("SWOT coverage is unavailable for this period.")
        return
    if summary.record_count == 0:
        st.info("No SWOT classifications exist in the selected period. The matrix is not filled artificially.")
    else:
        top = st.columns(3)
        top[0].metric("Evidence-backed classifications", summary.record_count or 0)
        top[1].metric("Internal factors", summary.internal_count or 0)
        top[2].metric("External factors", summary.external_count or 0)
        counts = dict(summary.category_counts)
        st.caption("Persisted classifications: " + " · ".join(f"{SWOT_DISPLAY_LABELS[key]}: {counts[key]}" for key in SWOT_ORDER))

        displayed_ids: set[str] = set()
        st.subheader("Internal factors")
        internal_columns = st.columns(2)
        for column, category in zip(internal_columns, SWOT_ORDER[:2]):
            with column:
                st.markdown(f"### {SWOT_DISPLAY_LABELS[category]}")
                items = select_swot_items(frame, category=category, scope="INTERNAL", filters=date_filters, limit=2)
                if items.empty:
                    st.caption("No persisted classification in this category.")
                else:
                    displayed_ids.update(items["swot_id"].astype(str))
                    for _, row in items.iterrows():
                        _render_item(st, row)
        st.subheader("External factors")
        external_columns = st.columns(2)
        for column, category in zip(external_columns, SWOT_ORDER[2:]):
            with column:
                st.markdown(f"### {SWOT_DISPLAY_LABELS[category]}")
                items = select_swot_items(frame, category=category, scope="EXTERNAL", filters=date_filters, limit=2)
                if items.empty:
                    st.caption("No persisted classification in this category.")
                else:
                    displayed_ids.update(items["swot_id"].astype(str))
                    for _, row in items.iterrows():
                        _render_item(st, row)

        all_items = select_swot_items(frame, filters=date_filters, limit=len(frame))
        additional_items = all_items.loc[~all_items["swot_id"].astype(str).isin(displayed_ids)]
        if not additional_items.empty:
            with st.expander("Additional classified factors"):
                for _, row in additional_items.iterrows():
                    st.markdown(f"**{SWOT_DISPLAY_LABELS[str(row.swot_category)]}**")
                    _render_item(st, row)
    st.caption("The page presents persisted categories only; it does not reclassify by numeric direction or recommend action.")
    with st.expander("Methodology and scope"):
        st.write("Strength/Weakness and Opportunity/Threat distinctions come from persisted SWOT scope/category fields. External SWOT records retain their PESTEL lineage.")
        st.write("An absent category is valid. Empty quadrants are not filled with inferred classifications, and this page does not produce causal claims or Product recommendations.")
        st.write("BCB household delinquency above 90 days is distinct from MercadoLibre's reported 15–90 day NPL.")
