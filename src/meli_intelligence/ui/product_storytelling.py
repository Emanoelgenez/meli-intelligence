"""Read-only presentation helpers for persisted Product Evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json

import pandas as pd

from meli_intelligence.product.evidence import PRODUCT_EVIDENCE_COLUMNS, PRODUCT_EVIDENCE_TYPES
from meli_intelligence.ui.filters import FilterState, apply_filters

HYPOTHESIS = "HYPOTHESIS"
DISCOVERY_QUESTION = "QUESTION_FOR_PRODUCT_DISCOVERY"
MAX_HYPOTHESES = 3
MAX_DISCOVERY_QUESTIONS = 5
PRODUCT_EVIDENCE_PRESENTATION_COLUMNS = tuple(PRODUCT_EVIDENCE_COLUMNS)
SUPPORTING_EVIDENCE_COLUMNS = (
    "evidence_id", "evidence_type", "business_domain", "metric_id", "reference_date", "claim", "source",
)


@dataclass(frozen=True)
class ProductEvidenceSummary:
    available: bool
    hypothesis_count: int | None
    question_count: int | None
    latest_reference_date: date | None


def _validated_frame(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None:
        return None
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Product Evidence input must be a pandas DataFrame or None.")
    if frame.empty:
        return frame.copy(deep=True)
    missing = set(PRODUCT_EVIDENCE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Product Evidence is missing columns: {sorted(missing)}")
    types = frame["product_evidence_type"]
    if types.isna().any():
        raise ValueError("Product Evidence type cannot be missing.")
    invalid = set(types.astype(str)).difference(PRODUCT_EVIDENCE_TYPES)
    if invalid:
        raise ValueError(f"Unsupported Product Evidence types: {sorted(invalid)}")
    if frame["product_evidence_id"].isna().any():
        raise ValueError("Product Evidence ID cannot be missing.")
    if frame["product_evidence_id"].astype(str).duplicated(keep=False).any():
        raise ValueError("Product Evidence IDs must be unique.")
    return frame.copy(deep=True)


def _filtered(frame: pd.DataFrame, filters: FilterState | None) -> pd.DataFrame:
    state = (filters or FilterState()).validate()
    # Product Evidence is explicitly cross-domain; a global business-domain filter
    # must not silently remove its Ecosystem records.
    date_state = FilterState(start_date=state.start_date, end_date=state.end_date)
    selected = apply_filters(frame, date_state)
    selected["_ui_reference_date"] = pd.to_datetime(selected["reference_date"], errors="coerce")
    return selected


def product_evidence_summary(
    frame: pd.DataFrame | None, *, filters: FilterState | None = None,
) -> ProductEvidenceSummary:
    validated = _validated_frame(frame)
    if validated is None:
        return ProductEvidenceSummary(False, None, None, None)
    selected = _filtered(validated, filters)
    types = selected["product_evidence_type"].astype(str) if "product_evidence_type" in selected else pd.Series(dtype=str)
    valid_dates = selected["_ui_reference_date"].dropna() if "_ui_reference_date" in selected else pd.Series(dtype="datetime64[ns]")
    latest = valid_dates.max()
    return ProductEvidenceSummary(
        True,
        int(types.eq(HYPOTHESIS).sum()),
        int(types.eq(DISCOVERY_QUESTION).sum()),
        latest.date() if pd.notna(latest) else None,
    )


def product_evidence_freshness(
    frame: pd.DataFrame | None, *, filters: FilterState | None = None,
) -> date | None:
    return product_evidence_summary(frame, filters=filters).latest_reference_date


def _select_type(
    frame: pd.DataFrame | None,
    evidence_type: str,
    *,
    filters: FilterState | None,
    limit: int,
) -> pd.DataFrame:
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("Product Evidence limit must be a non-negative integer.")
    validated = _validated_frame(frame)
    if validated is None:
        return pd.DataFrame(columns=PRODUCT_EVIDENCE_PRESENTATION_COLUMNS)
    if validated.empty:
        return validated
    selected = _filtered(validated, filters)
    selected = selected.loc[selected["product_evidence_type"].astype(str).eq(evidence_type)].copy()
    selected = selected.sort_values(
        ["_ui_reference_date", "product_evidence_id"],
        ascending=[False, True], na_position="last", kind="mergesort",
    )
    return selected.head(limit).drop(columns="_ui_reference_date").reset_index(drop=True)


def select_product_hypotheses(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    limit: int = MAX_HYPOTHESES,
) -> pd.DataFrame:
    return _select_type(frame, HYPOTHESIS, filters=filters, limit=limit)


def select_discovery_questions(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    limit: int = MAX_DISCOVERY_QUESTIONS,
) -> pd.DataFrame:
    return _select_type(frame, DISCOVERY_QUESTION, filters=filters, limit=limit)


def _lineage_ids(value: object) -> list[str]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Product Evidence lineage must contain a JSON array.") from exc
    else:
        decoded = value
    if not isinstance(decoded, (list, tuple, set)):
        raise ValueError("Product Evidence lineage must contain a JSON array.")
    return [str(item) for item in decoded]


def select_supporting_evidence(
    product_items: pd.DataFrame | None,
    evidence_registry: pd.DataFrame | None,
) -> pd.DataFrame:
    """Select only Evidence IDs explicitly named by the selected Product rows."""
    if product_items is None or product_items.empty or evidence_registry is None:
        return pd.DataFrame(columns=SUPPORTING_EVIDENCE_COLUMNS)
    if "source_evidence_ids" not in product_items.columns:
        raise ValueError("Product Evidence is missing source_evidence_ids lineage.")
    if "evidence_id" not in evidence_registry.columns:
        raise ValueError("Evidence registry is missing evidence_id.")
    lineage = {
        evidence_id
        for encoded in product_items["source_evidence_ids"]
        for evidence_id in _lineage_ids(encoded)
    }
    columns = [column for column in SUPPORTING_EVIDENCE_COLUMNS if column in evidence_registry.columns]
    if not lineage:
        return pd.DataFrame(columns=columns)
    selected = evidence_registry.loc[evidence_registry["evidence_id"].astype(str).isin(lineage), columns].copy()
    if "reference_date" in selected.columns:
        selected["_ui_reference_date"] = pd.to_datetime(selected["reference_date"], errors="coerce")
        selected = selected.sort_values(
            ["_ui_reference_date", "evidence_id"], ascending=[True, True],
            na_position="last", kind="mergesort",
        ).drop(columns="_ui_reference_date")
    else:
        selected = selected.sort_values("evidence_id", kind="mergesort")
    return selected.reset_index(drop=True)
