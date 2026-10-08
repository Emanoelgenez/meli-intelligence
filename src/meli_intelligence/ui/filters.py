"""Shared, validated UI filter state and DataFrame filtering helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

BUSINESS_DOMAINS = frozenset({
    "Financial", "Commerce", "Fintech", "Ecosystem", "Ads", "Logistics", "Macro", "Market",
})
DATE_COLUMNS = ("reference_date", "period_end", "date")


@dataclass(frozen=True)
class FilterState:
    business_domain: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    def validate(self) -> "FilterState":
        if self.business_domain is not None and self.business_domain not in BUSINESS_DOMAINS:
            raise ValueError(f"Unsupported business_domain: {self.business_domain}")
        if self.start_date is not None and not isinstance(self.start_date, date):
            raise ValueError("start_date must be a date.")
        if self.end_date is not None and not isinstance(self.end_date, date):
            raise ValueError("end_date must be a date.")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        return self


def apply_filters(frame: pd.DataFrame, filters: FilterState | None = None) -> pd.DataFrame:
    state = (filters or FilterState()).validate()
    result = frame.copy(deep=True)
    if state.business_domain is not None and "business_domain" in result.columns:
        result = result.loc[result.business_domain == state.business_domain].copy()
    date_column = next((column for column in DATE_COLUMNS if column in result.columns), None)
    if date_column is not None and (state.start_date is not None or state.end_date is not None):
        dates = pd.to_datetime(result[date_column], errors="coerce")
        mask = pd.Series(True, index=result.index)
        if state.start_date is not None:
            mask &= dates >= pd.Timestamp(state.start_date)
        if state.end_date is not None:
            mask &= dates <= pd.Timestamp(state.end_date)
        result = result.loc[mask].copy()
    return result.reset_index(drop=True)
