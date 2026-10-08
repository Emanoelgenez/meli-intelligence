"""Validate and normalize Twelve Data daily OHLCV observations."""
from __future__ import annotations

from datetime import date
import math
from typing import Any

import pandas as pd

from meli_intelligence.sources.market.twelve_data import TwelveDataFetch

ENTITY = "MercadoLibre, Inc."
SOURCE = "Twelve Data"
MARKET_PRICE_COLUMNS = (
    "ticker", "entity", "reference_date", "open", "high", "low", "close", "volume",
    "currency", "exchange", "mic_code", "source", "source_url", "retrieved_at",
    "source_bronze_file", "source_content_sha256",
)
CONFLICT_FIELDS = ("open", "high", "low", "close", "volume", "currency", "exchange")


def _number(value: Any, field: str, *, positive: bool) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Twelve Data {field} must be numeric.")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Twelve Data {field} must be numeric.") from None
    if not math.isfinite(result) or (positive and result <= 0) or (not positive and result < 0):
        requirement = "finite and greater than zero" if positive else "finite and nonnegative"
        raise ValueError(f"Twelve Data {field} must be {requirement}.")
    return result


def normalize_market_prices(
    fetch: TwelveDataFetch, *, source_bronze_file: str, source_content_sha256: str,
) -> pd.DataFrame:
    """Produce sorted Silver candidates without calendar filling or analytics."""
    meta = fetch.payload["meta"]
    if str(meta.get("symbol", "")).upper() != "MELI" or meta.get("interval") != "1day":
        raise ValueError("Unexpected Twelve Data symbol or interval.")
    currency, exchange = meta.get("currency"), meta.get("exchange")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("Twelve Data metadata is missing currency.")
    if not isinstance(exchange, str) or not exchange.strip():
        raise ValueError("Twelve Data metadata is missing exchange.")
    rows = []
    for index, item in enumerate(fetch.payload["values"]):
        if not isinstance(item, dict):
            raise ValueError(f"Twelve Data observation {index} must be an object.")
        try:
            ref_date = date.fromisoformat(str(item["datetime"]))
        except (KeyError, ValueError):
            raise ValueError(f"Twelve Data observation {index} has an invalid datetime.") from None
        ohlc = {name: _number(item.get(name), name, positive=True) for name in ("open", "high", "low", "close")}
        if ohlc["high"] < ohlc["low"] or not ohlc["low"] <= ohlc["open"] <= ohlc["high"]:
            raise ValueError(f"Twelve Data observation {index} has inconsistent OHLC range.")
        if not ohlc["low"] <= ohlc["close"] <= ohlc["high"]:
            raise ValueError(f"Twelve Data observation {index} has inconsistent close range.")
        raw_volume = item.get("volume")
        volume = None if raw_volume is None or raw_volume == "" else _number(raw_volume, "volume", positive=False)
        rows.append({
            "ticker": "MELI", "entity": ENTITY, "reference_date": ref_date,
            **ohlc, "volume": volume, "currency": currency.strip(), "exchange": exchange.strip(),
            "mic_code": str(meta["mic_code"]).strip() if meta.get("mic_code") else None,
            "source": SOURCE, "source_url": fetch.source_url, "retrieved_at": fetch.retrieved_at,
            "source_bronze_file": source_bronze_file, "source_content_sha256": source_content_sha256,
        })
    frame = pd.DataFrame(rows, columns=MARKET_PRICE_COLUMNS)
    if frame.empty:
        raise ValueError("Twelve Data returned no observations.")
    for _, group in frame.groupby(["ticker", "reference_date"], sort=False):
        if len(group) > 1:
            comparable = group[list(CONFLICT_FIELDS)].astype(object).where(pd.notna(group[list(CONFLICT_FIELDS)]), None)
            if len({tuple(row) for row in comparable.to_numpy().tolist()}) > 1:
                raise ValueError("Conflicting duplicate market economic key ticker + reference_date.")
    frame = frame.drop_duplicates(["ticker", "reference_date"], keep="first")
    return frame.sort_values(["ticker", "reference_date"], kind="mergesort").reset_index(drop=True)
