"""Pure presentation selectors for persisted market prices; no market analytics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import pandas as pd

from meli_intelligence.ui.filters import FilterState, apply_filters
from meli_intelligence.ui.presentation import format_metric

MARKET_PRICE_COLUMNS = (
    "ticker", "entity", "reference_date", "close", "currency", "source",
    "source_url", "retrieved_at",
)
MARKET_TICKER = "MELI"


@dataclass(frozen=True)
class MarketPrice:
    ticker: str
    entity: str
    reference_date: date
    close: float
    currency: str
    formatted_close: str
    source: str
    source_url: str
    retrieved_at: str


def _validate_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(MARKET_PRICE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Market price dataset is missing required columns: {sorted(missing)}")
    result = frame.copy(deep=True)
    result["reference_date"] = pd.to_datetime(result["reference_date"], errors="coerce")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    if result[list(MARKET_PRICE_COLUMNS)].isna().any().any():
        raise ValueError("Market price required fields cannot be null or invalid.")
    if not result.close.map(lambda value: math.isfinite(float(value)) and float(value) > 0).all():
        raise ValueError("Market close must be finite and greater than zero.")
    if result.ticker.astype(str).str.strip().eq("").any():
        raise ValueError("Market ticker cannot be empty.")
    for column in ("entity", "currency", "source", "source_url", "retrieved_at"):
        if result[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Market {column} cannot be empty.")
    if result.duplicated(["ticker", "reference_date"], keep=False).any():
        raise ValueError("Duplicate market economic key ticker + reference_date.")
    return result


def _select(frame: pd.DataFrame | None, filters: FilterState | None) -> pd.DataFrame:
    state = (filters or FilterState()).validate()
    if frame is None or frame.empty:
        return pd.DataFrame(columns=MARKET_PRICE_COLUMNS)
    validated = _validate_market_frame(frame)
    state = FilterState(start_date=state.start_date, end_date=state.end_date)
    result = apply_filters(validated, state)
    result = result.loc[result.ticker.astype(str).eq(MARKET_TICKER)].copy()
    return result.sort_values("reference_date", kind="mergesort").reset_index(drop=True)


def select_latest_market_price(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
) -> MarketPrice | None:
    selected = _select(frame, filters)
    if selected.empty:
        return None
    row = selected.iloc[-1]
    close = float(row.close)
    currency = str(row.currency)
    return MarketPrice(
        ticker=str(row.ticker),
        entity=str(row.entity),
        reference_date=pd.Timestamp(row.reference_date).date(),
        close=close,
        currency=currency,
        formatted_close=format_metric(close, currency),
        source=str(row.source),
        source_url=str(row.source_url),
        retrieved_at=str(row.retrieved_at),
    )


def select_market_trend(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
) -> pd.DataFrame:
    selected = _select(frame, filters)
    if selected.empty:
        return pd.DataFrame(columns=["reference_date", "close"])
    return selected[["reference_date", "close"]].reset_index(drop=True)


def market_freshness(frame: pd.DataFrame | None, *, filters: FilterState | None = None) -> date | None:
    latest = select_latest_market_price(frame, filters=filters)
    return latest.reference_date if latest else None
