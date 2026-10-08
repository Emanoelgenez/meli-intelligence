"""Typed, atomic Parquet storage and incremental merge for daily MELI prices."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import SILVER_DIR
from meli_intelligence.transformations.market_prices import CONFLICT_FIELDS, MARKET_PRICE_COLUMNS

SCHEMA_VERSION = "1"
DEFAULT_MARKET_PRICES_PATH = SILVER_DIR / "market" / "market_prices.parquet"
MARKET_PRICES_SCHEMA = pa.schema([
    pa.field("ticker", pa.string(), nullable=False),
    pa.field("entity", pa.string(), nullable=False),
    pa.field("reference_date", pa.date32(), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("volume", pa.float64(), nullable=True),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("exchange", pa.string(), nullable=False),
    pa.field("mic_code", pa.string(), nullable=True),
    pa.field("source", pa.string(), nullable=False),
    pa.field("source_url", pa.string(), nullable=False),
    pa.field("retrieved_at", pa.string(), nullable=False),
    pa.field("source_bronze_file", pa.string(), nullable=False),
    pa.field("source_content_sha256", pa.string(), nullable=False),
])
MARKET_PRICE_KEY = ("ticker", "reference_date")


def validate_market_prices(frame: pd.DataFrame) -> None:
    missing = set(MARKET_PRICE_COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"Market Silver is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Market Silver dataset cannot be empty.")
    required = [field.name for field in MARKET_PRICES_SCHEMA if not field.nullable]
    if frame[required].isna().any().any():
        raise ValueError("Market Silver required fields cannot be null.")
    if frame.duplicated(list(MARKET_PRICE_KEY), keep=False).any():
        raise ValueError("Duplicate market economic key ticker + reference_date.")
    if not frame.ticker.astype(str).eq("MELI").all():
        raise ValueError("Market Silver currently supports MELI only.")
    for field in ("open", "high", "low", "close"):
        values = pd.to_numeric(frame[field], errors="coerce")
        if values.isna().any() or not values.map(lambda value: math.isfinite(float(value)) and float(value) > 0).all():
            raise ValueError(f"Market Silver {field} must be finite and greater than zero.")
    volumes = pd.to_numeric(frame["volume"], errors="coerce")
    if (frame["volume"].notna() & (volumes.isna() | ~volumes.map(lambda value: math.isfinite(float(value)) if pd.notna(value) else True) | (volumes < 0))).any():
        raise ValueError("Market Silver volume must be finite and nonnegative when present.")
    if ((frame.high < frame.low) | (frame.open < frame.low) | (frame.open > frame.high)
            | (frame.close < frame.low) | (frame.close > frame.high)).any():
        raise ValueError("Market Silver contains inconsistent OHLC ranges.")
    parsed_dates = pd.to_datetime(frame.reference_date, errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("Market Silver reference_date contains invalid dates.")
    for column in ("entity", "currency", "exchange", "source", "source_url", "retrieved_at", "source_bronze_file", "source_content_sha256"):
        if frame[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Market Silver {column} cannot be empty.")
    if frame.source_url.astype(str).str.contains("apikey", case=False, regex=False).any():
        raise ValueError("Market Silver source_url must not contain API key parameters.")


def _normalized(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.loc[:, list(MARKET_PRICE_COLUMNS)].copy(deep=True)
    result["reference_date"] = pd.to_datetime(result["reference_date"]).dt.date
    for column in ("open", "high", "low", "close", "volume"):
        result[column] = pd.to_numeric(result[column], errors="raise").astype("float64")
    result["volume"] = result["volume"].where(pd.notna(result["volume"]), None)
    return result.sort_values(list(MARKET_PRICE_KEY), kind="mergesort").reset_index(drop=True)


def merge_market_prices(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Append new trading dates, preserve history, dedupe exact replays, fail conflicts."""
    validate_market_prices(incoming)
    fresh = _normalized(incoming)
    if existing.empty:
        return fresh
    validate_market_prices(existing)
    prior = _normalized(existing)
    overlap = prior.merge(fresh, on=list(MARKET_PRICE_KEY), suffixes=("_old", "_new"), validate="one_to_one")
    for _, row in overlap.iterrows():
        for field in CONFLICT_FIELDS:
            old, new = row[f"{field}_old"], row[f"{field}_new"]
            if pd.isna(old) and pd.isna(new):
                continue
            if pd.isna(old) != pd.isna(new) or old != new:
                raise ValueError("Incoming Market price conflicts with stored economic key ticker + reference_date.")
    new_rows = fresh.merge(prior[list(MARKET_PRICE_KEY)], on=list(MARKET_PRICE_KEY), how="left", indicator=True)
    new_rows = new_rows.loc[new_rows["_merge"] == "left_only", list(MARKET_PRICE_COLUMNS)]
    merged = pd.concat([prior, new_rows], ignore_index=True)
    validate_market_prices(merged)
    return _normalized(merged)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def write_market_prices(
    frame: pd.DataFrame, *, output_path: Path = DEFAULT_MARKET_PRICES_PATH,
    source_bronze_files: list[str] | None = None,
) -> tuple[Path, Path]:
    validate_market_prices(frame)
    prepared = _normalized(frame)
    table = pa.Table.from_pandas(prepared, schema=MARKET_PRICES_SCHEMA, preserve_index=False, safe=True)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp")
    os.close(fd)
    temp = Path(name)
    try:
        pq.write_table(table, temp, compression="zstd")
        os.replace(temp, output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    metadata_path = output.with_suffix(".metadata.json")
    _atomic_json(metadata_path, {
        "dataset": "market_prices", "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(), "row_count": table.num_rows,
        "sources": sorted(set(prepared.source.astype(str))), "parquet_file": output.name,
        "source_bronze_files": sorted(set(source_bronze_files or [])),
    })
    return output, metadata_path


def read_market_prices(path: Path = DEFAULT_MARKET_PRICES_PATH) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Market Silver Parquet not found: {path}")
    table = pq.read_table(path)
    if table.schema != MARKET_PRICES_SCHEMA:
        raise ValueError("Market Silver schema does not match the registered schema.")
    result = table.to_pandas()
    validate_market_prices(result)
    return result
