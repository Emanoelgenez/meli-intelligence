"""Evidence-backed PESTEL page; classifications are never recalculated here."""
from __future__ import annotations

import json

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import format_date
from meli_intelligence.ui.strategy_storytelling import PESTEL_ORDER, select_pestel_items, summarize_pestel


def _load(health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    item = next((row for row in health_records if row.dataset_id == "pestel"), None)
    if item is None or item.status != "AVAILABLE":
        return None, None if item is None else item.status, None
    try:
        return load_dataset("pestel", path=item.path, filters=filters), "AVAILABLE", None
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
    st.markdown(f"**{row.pestel_dimension} · {row.business_domain}**")
    st.write(str(row.claim))
    st.caption(f"{row.source} · {format_date(row.reference_date)} · {row.evidence_type if 'evidence_type' in row.index else 'Evidence-backed'}")
    with st.expander("Classification rationale and lineage"):
        st.write(str(row.classification_rationale))
        st.write("Source Evidence IDs: " + ", ".join(_list(row.source_evidence_ids)))
        if "source_evidence_types" in row.index:
            st.write("Source Evidence types: " + ", ".join(_list(row.source_evidence_types)))
        if "source_metric_ids" in row.index:
            st.write("Source metric IDs: " + ", ".join(_list(row.source_metric_ids)))
        st.write(f"Definition context: {row.definition_context}")


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date)
    frame, status, error = _load(health_records, date_filters)
    st.title("PESTEL")
    st.caption("Which external forces are supported by the current evidence base?")
    if status != "AVAILABLE":
        st.warning(f"PESTEL dataset status: {status or 'MISSING'}. No classifications are fabricated.")
        if error:
            st.caption(f"Read diagnostic: {error}")
        return
    try:
        summary = summarize_pestel(frame, filters=date_filters)
    except ValueError as exc:
        st.error(f"PESTEL data could not be presented: {exc}")
        return
    st.caption(f"Latest reference date: {format_date(summary.latest_reference_date)}")
    if not summary.available:
        st.info("PESTEL coverage is unavailable for this period.")
        return
    first = st.columns(2)
    first[0].metric("Classified evidence records", summary.record_count or 0)
    first[1].metric("Dimensions with evidence", len(summary.covered_dimensions))
    if summary.record_count == 0:
        st.info("No PESTEL classifications exist in the selected period. Empty dimensions are not populated artificially.")
    else:
        covered = ", ".join(summary.covered_dimensions) if summary.covered_dimensions else "None"
        st.caption(f"Evidence-backed dimensions: {covered}")
        st.caption("Dimensions without evidence: " + (", ".join(summary.absent_dimensions) if summary.absent_dimensions else "None"))
        selected = select_pestel_items(frame, filters=date_filters, limit=4)
        for _, row in selected.iterrows():
            _render_item(st, row)
        if len(frame) > len(selected):
            with st.expander("All classified evidence"):
                all_items = select_pestel_items(frame, filters=date_filters, limit=len(frame))
                for _, row in all_items.iloc[len(selected):].iterrows():
                    _render_item(st, row)
    st.caption("PESTEL describes persisted Evidence classifications; it does not create facts, causal claims or recommendations.")
    with st.expander("PESTEL dimension order and methodology"):
        st.write("Dimension order: " + " → ".join(PESTEL_ORDER))
        st.write("The layer uses only stored classifications and their Evidence lineage. Political, Environmental and Legal dimensions remain absent when no supporting Evidence exists.")
