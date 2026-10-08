"""Discovery-facing presentation of persisted Product Evidence records."""
from __future__ import annotations

import json

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import format_date, unavailable_message
from meli_intelligence.ui.product_storytelling import (
    DISCOVERY_QUESTION,
    HYPOTHESIS,
    product_evidence_freshness,
    product_evidence_summary,
    select_discovery_questions,
    select_product_hypotheses,
    select_supporting_evidence,
)

PRODUCT_DATASET_ID = "product_evidence"
EVIDENCE_DATASET_ID = "evidence_registry"


def _load_dataset(dataset_id: str, health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    item = next((record for record in health_records if record.dataset_id == dataset_id), None)
    if item is None:
        return None, "MISSING", None
    if item.status != "AVAILABLE":
        return None, item.status, None
    try:
        return load_dataset(dataset_id, path=item.path, filters=filters), "AVAILABLE", None
    except Exception as exc:
        return None, "INVALID", type(exc).__name__


def _lineage(value: object) -> list[str]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return list(map(str, decoded)) if isinstance(decoded, list) else []
    return list(map(str, value))


def _period_label(row) -> str:
    start = format_date(row.get("period_start"))
    end = format_date(row.get("period_end"))
    if start != "Unavailable" or end != "Unavailable":
        if start == end:
            return start
        return f"{start} – {end}"
    period_value = row.get("period_type")
    period_type = "Period not reported" if period_value is None or pd.isna(period_value) else str(period_value)
    return period_type.replace("_", " ").capitalize()


def _render_record(st, row, label: str) -> None:
    st.markdown(f"**{label}**")
    st.write(str(row.statement))
    st.caption(
        f"{row.business_domain} · {row.discovery_theme} · {format_date(row.reference_date)} · {_period_label(row)}"
    )
    with st.expander("Rationale, lineage and definition"):
        st.write(str(row.rationale))
        st.write("Source: " + str(row.source))
        st.write("Source Evidence IDs: " + ", ".join(_lineage(row.source_evidence_ids)))
        interpretation_ids = _lineage(row.source_interpretation_ids)
        if interpretation_ids:
            st.write("Source Interpretation IDs: " + ", ".join(interpretation_ids))
        pestel_ids = _lineage(row.source_pestel_ids)
        if pestel_ids:
            st.write("Source PESTEL IDs: " + ", ".join(pestel_ids))
        swot_ids = _lineage(row.source_swot_ids)
        if swot_ids:
            st.write("Source SWOT IDs: " + ", ".join(swot_ids))
        hypothesis_ids = _lineage(row.source_hypothesis_ids)
        if hypothesis_ids:
            st.write("Linked hypothesis IDs: " + ", ".join(hypothesis_ids))
        st.write("Source metric IDs: " + ", ".join(_lineage(row.source_metric_ids)))
        st.write(f"Definition context: {row.definition_context}")
        st.caption(f"Methodology version: {row.methodology_version} · Scope: {row.scope}")


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date)
    frame, status, error = _load_dataset(PRODUCT_DATASET_ID, health_records, date_filters)

    st.title("Product Evidence")
    st.caption(
        "What evidence-backed hypotheses and discovery questions currently exist around ecosystem engagement, and what remains unknown?"
    )
    st.write(
        "This page presents persisted discovery records. Hypotheses are not validated Product problems; discovery questions remain open."
    )
    if status != "AVAILABLE":
        st.caption("Latest reference date: Unavailable")
        st.warning(unavailable_message(
            "Product Evidence data status", status,
            boundary="No hypotheses or questions are fabricated.",
        ))
        if error:
            st.caption(f"Read diagnostic: {error}")
        st.subheader("What remains unknown")
        st.write("Aggregate business metrics do not establish user-level overlap, cross-domain retention or individual activity patterns.")
        return

    try:
        summary = product_evidence_summary(frame, filters=date_filters)
        hypotheses = select_product_hypotheses(frame, filters=date_filters)
        questions = select_discovery_questions(frame, filters=date_filters)
        freshness = product_evidence_freshness(frame, filters=date_filters)
    except (TypeError, ValueError) as exc:
        st.caption("Latest reference date: Unavailable")
        st.error(f"Product Evidence could not be presented: {exc}")
        return

    st.caption(f"Latest reference date: {format_date(freshness)}")
    overview = st.columns(3)
    overview[0].metric("Dataset status", "Available")
    overview[1].metric("Hypotheses", summary.hypothesis_count)
    overview[2].metric("Discovery questions", summary.question_count)

    if status == "EMPTY" or (summary.hypothesis_count == 0 and summary.question_count == 0):
        st.info("No persisted Product Evidence records exist for the selected period.")

    st.subheader("Hypotheses")
    if hypotheses.empty:
        st.info("No persisted hypotheses are available for this period.")
    else:
        for _, row in hypotheses.iterrows():
            _render_record(st, row, "Hypothesis")

    if summary.hypothesis_count is not None and summary.hypothesis_count > len(hypotheses):
        with st.expander("Additional hypotheses"):
            remaining = select_product_hypotheses(
                frame, filters=date_filters, limit=summary.hypothesis_count
            ).iloc[len(hypotheses):]
            for _, row in remaining.iterrows():
                _render_record(st, row, "Hypothesis")

    st.subheader("Questions for Product Discovery")
    if questions.empty:
        st.info("No persisted discovery questions are available for this period.")
    else:
        for _, row in questions.iterrows():
            _render_record(st, row, "Question for Product Discovery")
            st.caption("This question remains open; the page does not answer it or propose a solution.")

    if summary.question_count is not None and summary.question_count > len(questions):
        with st.expander("Additional discovery questions"):
            remaining = select_discovery_questions(
                frame, filters=date_filters, limit=summary.question_count
            ).iloc[len(questions):]
            for _, row in remaining.iterrows():
                _render_record(st, row, "Question for Product Discovery")

    if not hypotheses.empty or not questions.empty:
        if st.checkbox("Show linked source Evidence records", value=False):
            evidence_frame, evidence_status, evidence_error = _load_dataset(
                EVIDENCE_DATASET_ID, health_records, date_filters
            )
            if evidence_status != "AVAILABLE":
                st.info(
                    f"Evidence registry status: {evidence_status}. Explicit source IDs remain available in each record's lineage."
                )
                if evidence_error:
                    st.caption(f"Read diagnostic: {evidence_error}")
            else:
                visible_product_items = pd.concat([hypotheses, questions], ignore_index=True)
                try:
                    supporting = select_supporting_evidence(visible_product_items, evidence_frame)
                except (TypeError, ValueError) as exc:
                    st.warning(f"Linked Evidence could not be displayed: {exc}")
                else:
                    if supporting.empty:
                        st.info("No Evidence records matching the explicitly stored lineage IDs were found.")
                    else:
                        st.dataframe(supporting, width="stretch", hide_index=True)

    st.subheader("What remains unknown")
    st.write(
        "Buyers, Fintech MAU, GMV, TPV, AUM and credit are aggregate measures. "
        "They do not, by themselves, establish whether the same people use Commerce and Fintech, "
        "individual cross-domain retention or frequency, cross-sell, or a count of ecosystem users."
    )
    st.caption("No overlap estimate, synthetic ecosystem-user count or engagement score is produced.")
    with st.expander("Methodology and limits"):
        st.write("Hypotheses and discovery questions shown here are records already persisted in Product Evidence Gold.")
        st.write("Supporting Evidence is shown only when its ID is explicitly present in source_evidence_ids; FACT, OBSERVATION and INTERPRETATION labels are preserved from the Evidence registry.")
        st.write("Aggregate metrics do not establish user-level overlap or causal relationships. A discovery question is not an answer, recommendation or Product solution.")
        st.write("Date filters use reference_date. Retrieval and file timestamps are not treated as business freshness.")
