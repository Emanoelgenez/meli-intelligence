"""Dataset health, paths, and existing source lineage visibility."""
from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.data import load_dataset
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import format_date, format_status

_LINEAGE_COLUMNS = (
    "source", "source_url", "metric_id", "source_metric_id", "source_series_id", "source_evidence_ids",
    "source_pestel_ids", "source_swot_ids", "source_hypothesis_ids", "source_bronze_file",
    "retrieved_at", "filed_at", "accession_number",
)


def health_rows(health_records, catalog) -> pd.DataFrame:
    specs = {spec.dataset_id: spec for spec in catalog}
    records = []
    for item in health_records:
        spec = specs[item.dataset_id]
        records.append({
            "dataset_id": item.dataset_id, "display_name": spec.display_name,
            "layer": spec.layer, "business_domain": ", ".join(spec.business_domains) or "—",
            "status": format_status(item.status), "rows": item.row_count, "columns": item.column_count,
            "latest_reference_date": format_date(item.latest_reference_date), "message": item.message,
        })
    return pd.DataFrame(records)


def source_preview(
    dataset_id: str,
    *,
    path=None,
    limit: int = 5,
    filters: FilterState | None = None,
) -> pd.DataFrame:
    frame = load_dataset(dataset_id, path=path, filters=filters)
    columns = [column for column in _LINEAGE_COLUMNS if column in frame.columns]
    if not columns:
        return pd.DataFrame({"message": ["No source/lineage columns are present."]})
    return frame.loc[:, columns].head(limit).copy()


def render(st, health_records, catalog, filters: FilterState | None = None) -> None:
    st.title("Data Quality & Sources")
    st.caption("Availability, freshness, and lineage are read from local datasets and existing source metadata.")
    rows = health_rows(health_records, catalog)
    state = (filters or FilterState()).validate()
    if state.business_domain is not None:
        selected = {
            spec.dataset_id for spec in catalog
            if state.business_domain in spec.business_domains
        }
        rows = rows.loc[rows.dataset_id.isin(selected)].reset_index(drop=True)
    st.dataframe(
        rows.drop(columns=["message"], errors="ignore"),
        width="stretch",
        hide_index=True,
    )
    for item in health_records:
        if state.business_domain is not None:
            spec = next(spec for spec in catalog if spec.dataset_id == item.dataset_id)
            if state.business_domain not in spec.business_domains:
                continue
        if item.status != "AVAILABLE":
            with st.expander(f"{item.dataset_id} — {format_status(item.status)}"):
                st.write(item.message)
                st.caption(f"Path: {item.path}")
            continue
        with st.expander(f"Details and source fields — {item.dataset_id}"):
            st.caption(f"{format_status(item.status)} · Path: {item.path}")
            st.write(item.message)
            try:
                preview = source_preview(item.dataset_id, path=item.path, filters=filters)
                st.dataframe(preview, width="stretch", hide_index=True)
            except Exception as exc:
                st.info(f"Lineage preview unavailable ({type(exc).__name__}).")
