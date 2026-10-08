"""Macro context page using existing normalized and derived datasets."""
from __future__ import annotations

import json

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.macro_storytelling import (
    MACRO_ADDITIONAL,
    MACRO_PRIORITY,
    MACRO_TREND_METRICS,
    macro_freshness,
    select_macro_observations,
    select_macro_snapshots,
    select_macro_trend,
)
from meli_intelligence.ui.presentation import format_date, select_latest_interpretations

DATASET_IDS = ("macro_indicators", "macro_analytics", "macro_evidence", "interpretations")


def _load(health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    health_by_id = {item.dataset_id: item for item in health_records}
    frames: dict[str, pd.DataFrame | None] = {}
    failures = []
    for dataset_id in DATASET_IDS:
        item = health_by_id.get(dataset_id)
        if item is None or item.status != "AVAILABLE":
            frames[dataset_id] = None
            continue
        try:
            frames[dataset_id] = load_dataset(dataset_id, path=item.path, filters=filters)
        except Exception as exc:
            frames[dataset_id] = None
            failures.append(f"{dataset_id}: {type(exc).__name__}")
    statuses = tuple(
        f"{dataset_id}: {health_by_id[dataset_id].status}"
        for dataset_id in DATASET_IDS
        if dataset_id in health_by_id and health_by_id[dataset_id].status != "AVAILABLE"
    )
    return frames, statuses, failures


def _format_frequency(value: str) -> str:
    labels = {
        "daily": "Daily",
        "monthly": "Monthly",
        "rolling_3m_monthly": "Monthly publication · rolling three-month rate",
    }
    return labels.get(value, value.replace("_", " ").capitalize() if value else "Frequency not reported")


def _lineage_values(row, column: str) -> list[str]:
    value = row.get(column)
    if value is None or pd.isna(value):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return list(map(str, parsed)) if isinstance(parsed, list) else [str(parsed)]
    return list(map(str, value))


def render(st, health_records, catalog=None, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date)
    frames, degraded, failures = _load(health_records, date_filters)
    st.title("Macro")
    st.caption("What does the current Brazilian macro environment say about the operating context around MercadoLibre?")

    latest = macro_freshness(frames, filters=date_filters)
    st.caption(f"Latest applicable reference date: {format_date(latest)}")
    if degraded:
        st.warning("Macro data availability is limited: " + "; ".join(degraded) + ".")
    if failures:
        st.warning("Some macro datasets could not be read: " + "; ".join(failures) + ".")

    st.subheader("Key macro conditions")
    priority_ids = tuple(spec.metric_id for spec in MACRO_PRIORITY)
    snapshots = select_macro_snapshots(frames, filters=date_filters, metric_ids=priority_ids)
    if snapshots:
        columns = st.columns(min(4, len(snapshots)))
        for column, snapshot in zip(columns, snapshots):
            with column:
                st.metric(snapshot.display_name, snapshot.formatted_value)
                st.caption(f"{_format_frequency(snapshot.frequency)} · Reference date: {format_date(snapshot.reference_date)}")
                st.caption(snapshot.context)
                with st.expander("Source and reported precision"):
                    st.write(f"Source: {snapshot.source}")
                    st.write(f"Value as loaded: {snapshot.full_precision_value}")
                    if snapshot.source_url:
                        st.write(f"Source URL: {snapshot.source_url}")
    else:
        st.info("No priority Macro observations are available in the selected period. Missing values are not substituted with zero.")
    available_primary = {item.metric_id for item in snapshots}
    missing_primary = [spec.label for spec in MACRO_PRIORITY if spec.metric_id not in available_primary]
    if missing_primary:
        st.caption("Priority measures unavailable for this period: " + ", ".join(missing_primary) + ".")

    trend_id = next(iter(MACRO_TREND_METRICS))
    trend_spec = next(spec for spec in MACRO_PRIORITY if spec.metric_id == trend_id)
    trend = select_macro_trend(frames, metric_id=trend_id, filters=date_filters)
    st.subheader("Target Selic rate · daily reported observations")
    if trend.empty:
        st.info(f"No reported {trend_spec.label} observations are available for this period.")
    else:
        st.caption("Target Selic · daily reported observations. Original dates are preserved; no resampling, interpolation or change calculation is applied.")
        st.line_chart(trend, x="reference_date", y="value", x_label="Reference date", y_label=trend_spec.label)

    st.subheader("Existing Macro observations")
    observations = select_macro_observations(frames.get("macro_evidence"), filters=date_filters)
    if observations.empty:
        st.info("No persisted Macro observations are available for the selected period.")
    else:
        for _, row in observations.iterrows():
            st.markdown(f"**Observation · {MACRO_LABEL_FOR(str(row.metric_id))}**")
            st.write(str(row.claim))
            st.caption(f"{row.source} · {format_date(row.reference_date)} · Evidence ID: {row.evidence_id}")

    interpretation_frame = frames.get("interpretations")
    if interpretation_frame is not None and "business_domain" in interpretation_frame.columns:
        interpretation_frame = interpretation_frame.loc[interpretation_frame.business_domain.astype(str) == "Macro"].copy()
    interpretations = select_latest_interpretations(interpretation_frame, filters=date_filters, limit=3)
    st.subheader("Existing interpretations")
    if not interpretations:
        st.info("No existing Macro interpretation is available for the selected period.")
    else:
        for item in interpretations:
            st.markdown(f"**Interpretation · {MACRO_LABEL_FOR(item.metric_id)}**")
            st.write(item.claim)
            st.caption(f"{item.source} · {format_date(item.reference_date)} · Evidence ID: {item.evidence_id}")

    with st.expander("Additional Macro context"):
        extra_ids = tuple(spec.metric_id for spec in MACRO_ADDITIONAL)
        additional = select_macro_snapshots(
            frames, filters=date_filters, metric_ids=extra_ids, limit=len(MACRO_ADDITIONAL)
        )
        if not additional:
            st.info("No additional persisted Macro facts or analytics are available for this period.")
        else:
            table = pd.DataFrame([
                {
                    "Measure": row.display_name,
                    "Reported value": row.formatted_value,
                    "Frequency": _format_frequency(row.frequency),
                    "Reference date": format_date(row.reference_date),
                    "Source": row.source,
                }
                for row in additional
            ])
            st.dataframe(table, width="stretch", hide_index=True)
            st.caption("Derived values in this list are read from existing Macro Analytics Gold; the UI does not recalculate them.")

    with st.expander("Methodology and limits"):
        st.write("Macro Silver facts remain the source for reported levels. Gold analytics are shown only when already persisted. Daily, monthly and rolling-three-month frequencies remain distinct.")
        st.write("The IBC-Br is an activity indicator, not GDP. Unemployment is a rolling three-month publication with overlapping windows. BCB household delinquency above 90 days is distinct from MercadoLibre's 15–90 day NPL.")
        st.write("Macro indicators describe context; this page does not introduce causal claims or Product recommendations.")
    st.caption("Date filters use economic reference dates, not retrieval timestamps.")


def MACRO_LABEL_FOR(metric_id: str) -> str:
    from meli_intelligence.ui.macro_storytelling import MACRO_LABELS

    return MACRO_LABELS.get(metric_id, "Macro measure")
