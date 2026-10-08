"""Pure helpers for the Executive Overview narrative and progressive disclosure."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from meli_intelligence.ui.presentation import (
    executive_summary,
    format_status,
    latest_global_reference_date,
)

CENTRAL_QUESTION = "What does the current evidence say about MercadoLibre's business, ecosystem and operating context?"
EXECUTIVE_CONTEXT = (
    "MELI Intelligence brings together financial, operational, macroeconomic and strategic evidence "
    "to support structured investigation of MercadoLibre. It presents available evidence; it does not recommend decisions."
)
STORY_FLOW = ("Context", "Status", "Evidence", "Interpretation", "Next exploration")


@dataclass(frozen=True)
class CoverageSummary:
    available: int
    total: int
    latest_reference_date: object
    degraded: bool
    message: str | None


def build_coverage_summary(health_records, degraded_message: str | None = None) -> CoverageSummary:
    summary = executive_summary(health_records)
    return CoverageSummary(
        available=summary.available_count,
        total=summary.dataset_count,
        latest_reference_date=latest_global_reference_date(health_records),
        degraded=summary.degraded,
        message=degraded_message,
    )


def availability_frame(health_records, catalog) -> pd.DataFrame:
    spec_by_id = {spec.dataset_id: spec for spec in catalog}
    records = []
    for item in health_records:
        spec = spec_by_id[item.dataset_id]
        for domain in spec.business_domains or ("Unassigned",):
            records.append({"business_domain": domain, "layer": spec.layer, "status": format_status(item.status)})
    columns = ["business_domain", "layer", "status", "dataset_count"]
    if not records:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(records)
        .groupby(["business_domain", "layer", "status"], as_index=False)
        .size()
        .rename(columns={"size": "dataset_count"})
        .sort_values(["business_domain", "layer", "status"], kind="mergesort")
        .reset_index(drop=True)
    )


def count_strategy_records(frame: pd.DataFrame | None, id_column: str) -> int:
    if frame is None or frame.empty or id_column not in frame.columns:
        return 0
    return int(frame[id_column].nunique())
