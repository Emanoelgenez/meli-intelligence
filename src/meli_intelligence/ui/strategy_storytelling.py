"""Presentation helpers for persisted PESTEL and SWOT classifications."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from meli_intelligence.strategy.pestel import PESTEL_DIMENSIONS
from meli_intelligence.strategy.swot import SWOT_CATEGORIES
from meli_intelligence.ui.filters import FilterState, apply_filters

PESTEL_ORDER = ("POLITICAL", "ECONOMIC", "SOCIAL", "TECHNOLOGICAL", "ENVIRONMENTAL", "LEGAL")
SWOT_ORDER = ("STRENGTH", "WEAKNESS", "OPPORTUNITY", "THREAT")
SWOT_DISPLAY_LABELS = {
    "STRENGTH": "Strength",
    "WEAKNESS": "Weakness",
    "OPPORTUNITY": "Opportunity",
    "THREAT": "Threat",
}


@dataclass(frozen=True)
class PESTELSummary:
    available: bool
    record_count: int | None
    covered_dimensions: tuple[str, ...]
    absent_dimensions: tuple[str, ...]
    dimension_counts: tuple[tuple[str, int], ...]
    latest_reference_date: date | None


@dataclass(frozen=True)
class SWOTSummary:
    available: bool
    record_count: int | None
    category_counts: tuple[tuple[str, int], ...]
    internal_count: int | None
    external_count: int | None
    latest_reference_date: date | None


def _filtered(frame: pd.DataFrame | None, date_column: str, filters: FilterState | None) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty:
        return frame.copy(deep=True)
    if date_column not in frame.columns:
        raise ValueError(f"Strategy dataset is missing temporal column {date_column!r}.")
    state = (filters or FilterState()).validate()
    return apply_filters(frame, FilterState(start_date=state.start_date, end_date=state.end_date))


def summarize_pestel(frame: pd.DataFrame | None, *, filters: FilterState | None = None) -> PESTELSummary:
    if frame is None:
        return PESTELSummary(False, None, (), (), (), None)
    selected = _filtered(frame, "reference_date", filters)
    if selected.empty:
        return PESTELSummary(True, 0, (), PESTEL_ORDER, tuple((dimension, 0) for dimension in PESTEL_ORDER), None)
    required = {"pestel_id", "pestel_dimension", "reference_date"}
    missing = required.difference(selected.columns)
    if missing:
        raise ValueError(f"PESTEL dataset missing columns: {sorted(missing)}")
    dimensions = set(selected.pestel_dimension.astype(str))
    invalid = dimensions.difference(PESTEL_DIMENSIONS)
    if invalid:
        raise ValueError(f"PESTEL dataset contains unsupported dimensions: {sorted(invalid)}")
    counts = tuple((dimension, int(selected.pestel_dimension.astype(str).eq(dimension).sum())) for dimension in PESTEL_ORDER)
    latest = pd.to_datetime(selected.reference_date, errors="coerce").max()
    return PESTELSummary(
        True,
        len(selected),
        tuple(dimension for dimension in PESTEL_ORDER if dimension in dimensions),
        tuple(dimension for dimension in PESTEL_ORDER if dimension not in dimensions),
        counts,
        latest.date() if pd.notna(latest) else None,
    )


def select_pestel_items(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    limit: int = 4,
) -> pd.DataFrame:
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("PESTEL item limit must be a non-negative integer.")
    if frame is None or frame.empty:
        return frame.copy(deep=True) if frame is not None else pd.DataFrame()
    required = {"pestel_id", "pestel_dimension", "reference_date", "claim", "source_evidence_ids"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"PESTEL dataset missing columns: {sorted(missing)}")
    selected = _filtered(frame, "reference_date", filters).copy()
    invalid = set(selected.pestel_dimension.astype(str)).difference(PESTEL_DIMENSIONS)
    if invalid:
        raise ValueError(f"PESTEL dataset contains unsupported dimensions: {sorted(invalid)}")
    order = {dimension: index for index, dimension in enumerate(PESTEL_ORDER)}
    selected["_ui_dimension_order"] = selected.pestel_dimension.astype(str).map(order)
    selected["_ui_date"] = pd.to_datetime(selected.reference_date, errors="coerce")
    selected = selected.sort_values(
        ["_ui_dimension_order", "_ui_date", "pestel_id"],
        ascending=[True, False, True], kind="mergesort",
    )
    return selected.head(limit).drop(columns=["_ui_dimension_order", "_ui_date"]).reset_index(drop=True)


def summarize_swot(frame: pd.DataFrame | None, *, filters: FilterState | None = None) -> SWOTSummary:
    if frame is None:
        return SWOTSummary(False, None, (), None, None, None)
    selected = _filtered(frame, "reference_date", filters)
    if selected.empty:
        return SWOTSummary(True, 0, tuple((category, 0) for category in SWOT_ORDER), 0, 0, None)
    required = {"swot_id", "swot_category", "scope", "reference_date"}
    missing = required.difference(selected.columns)
    if missing:
        raise ValueError(f"SWOT dataset missing columns: {sorted(missing)}")
    categories = set(selected.swot_category.astype(str))
    invalid = categories.difference(SWOT_CATEGORIES)
    if invalid:
        raise ValueError(f"SWOT dataset contains unsupported categories: {sorted(invalid)}")
    scopes = set(selected.scope.astype(str))
    if not scopes.issubset({"INTERNAL", "EXTERNAL"}):
        raise ValueError(f"SWOT dataset contains unsupported scopes: {sorted(scopes)}")
    counts = tuple((category, int(selected.swot_category.astype(str).eq(category).sum())) for category in SWOT_ORDER)
    latest = pd.to_datetime(selected.reference_date, errors="coerce").max()
    return SWOTSummary(
        True,
        len(selected),
        counts,
        int(selected.scope.astype(str).eq("INTERNAL").sum()),
        int(selected.scope.astype(str).eq("EXTERNAL").sum()),
        latest.date() if pd.notna(latest) else None,
    )


def select_swot_items(
    frame: pd.DataFrame | None,
    *,
    category: str | None = None,
    scope: Literal["INTERNAL", "EXTERNAL"] | None = None,
    filters: FilterState | None = None,
    limit: int = 2,
) -> pd.DataFrame:
    if category is not None and category not in SWOT_CATEGORIES:
        raise ValueError(f"Invalid SWOT category: {category}")
    if scope is not None and scope not in {"INTERNAL", "EXTERNAL"}:
        raise ValueError(f"Invalid SWOT scope: {scope}")
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("SWOT item limit must be a non-negative integer.")
    if frame is None or frame.empty:
        return frame.copy(deep=True) if frame is not None else pd.DataFrame()
    required = {"swot_id", "swot_category", "scope", "reference_date", "claim", "assessment", "source_evidence_ids"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"SWOT dataset missing columns: {sorted(missing)}")
    selected = _filtered(frame, "reference_date", filters).copy()
    if category is not None:
        selected = selected.loc[selected.swot_category.astype(str) == category].copy()
    if scope is not None:
        selected = selected.loc[selected.scope.astype(str) == scope].copy()
    invalid = set(selected.swot_category.astype(str)).difference(SWOT_CATEGORIES)
    if invalid:
        raise ValueError(f"SWOT dataset contains unsupported categories: {sorted(invalid)}")
    order = {name: index for index, name in enumerate(SWOT_ORDER)}
    selected["_ui_category_order"] = selected.swot_category.astype(str).map(order)
    selected["_ui_date"] = pd.to_datetime(selected.reference_date, errors="coerce")
    selected = selected.sort_values(
        ["_ui_category_order", "_ui_date", "swot_id"],
        ascending=[True, False, True], kind="mergesort",
    )
    return selected.head(limit).drop(columns=["_ui_category_order", "_ui_date"]).reset_index(drop=True)


def pestel_navigation_order() -> tuple[str, ...]:
    return PESTEL_ORDER


def swot_navigation_order() -> tuple[str, ...]:
    return SWOT_ORDER
