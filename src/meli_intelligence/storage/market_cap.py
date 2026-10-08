"""Typed Gold persistence for derived historical market capitalization."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.analytics.market_cap import (
    MARKET_CAP_GOLD_COLUMNS,
    MARKET_CAP_STATUSES,
    STATUS_AVAILABLE,
)
from meli_intelligence.config.settings import GOLD_DIR

SCHEMA_VERSION = "1"
DEFAULT_MARKET_CAP_PATH = GOLD_DIR / "market" / "market_capitalization.parquet"
MARKET_CAP_SCHEMA = pa.schema([
    pa.field("ticker", pa.string(), nullable=False),
    pa.field("entity", pa.string(), nullable=False),
    pa.field("reference_date", pa.date32(), nullable=False),
    pa.field("value", pa.float64(), nullable=True),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("status", pa.string(), nullable=False),
    pa.field("reason", pa.string(), nullable=True),
    pa.field("price", pa.float64(), nullable=True),
    pa.field("shares_outstanding", pa.float64(), nullable=True),
    pa.field("shares_reference_date", pa.date32(), nullable=True),
    pa.field("shares_filed_at", pa.date32(), nullable=True),
    pa.field("shares_accession_number", pa.string(), nullable=True),
    pa.field("source_metric_ids", pa.string(), nullable=False),
    pa.field("market_source", pa.string(), nullable=False),
    pa.field("market_source_url", pa.string(), nullable=False),
    pa.field("market_retrieved_at", pa.string(), nullable=False),
    pa.field("market_source_bronze_file", pa.string(), nullable=True),
    pa.field("market_source_content_sha256", pa.string(), nullable=True),
    pa.field("shares_source", pa.string(), nullable=True),
    pa.field("shares_source_url", pa.string(), nullable=True),
    pa.field("methodology_version", pa.string(), nullable=False),
])
MARKET_CAP_KEY = ("ticker", "reference_date")
_ANALYTICAL_FIELDS = tuple(
    column for column in MARKET_CAP_GOLD_COLUMNS
    if column not in {"market_retrieved_at"}
)


def _prepare(rows: pd.DataFrame) -> pd.DataFrame:
    missing = set(MARKET_CAP_GOLD_COLUMNS).difference(rows.columns)
    if missing:
        raise ValueError(f"Market Cap Gold is missing columns: {sorted(missing)}")
    frame = rows.loc[:, list(MARKET_CAP_GOLD_COLUMNS)].copy(deep=True)
    if frame.empty:
        raise ValueError("Market Cap Gold cannot be empty.")
    # Normalize pandas dtypes from the Arrow schema before validation, merge,
    # equality checks, or serialization. In particular, an all-null Arrow
    # string column can arrive from pandas as either object or StringDtype.
    for field in MARKET_CAP_SCHEMA:
        column = field.name
        if pa.types.is_string(field.type):
            normalized = frame[column].astype("object")
            frame[column] = normalized.where(pd.notna(normalized), None)
        elif pa.types.is_date32(field.type):
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
        elif pa.types.is_float64(field.type):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    if frame.reference_date.isna().any():
        raise ValueError("Market Cap Gold reference_date must be valid.")
    if frame[list(MARKET_CAP_KEY)].isna().any().any():
        raise ValueError("Market Cap Gold economic key cannot be null.")
    if frame.duplicated(list(MARKET_CAP_KEY), keep=False).any():
        raise ValueError("Duplicate Market Cap Gold ticker + reference_date key.")
    if not frame.status.astype(str).isin(MARKET_CAP_STATUSES).all():
        raise ValueError("Market Cap Gold contains an unsupported availability status.")
    required = [
        "ticker", "entity", "currency", "status",
        "market_source", "market_source_url", "market_retrieved_at", "methodology_version",
    ]
    if frame[required].isna().any().any():
        raise ValueError("Market Cap Gold required fields cannot be null.")
    for column in required:
        if frame[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Market Cap Gold {column} cannot be empty.")
    available = frame.status.eq(STATUS_AVAILABLE)
    available_fields = [
        "value", "price", "shares_outstanding", "shares_reference_date", "shares_filed_at",
        "shares_accession_number", "shares_source", "shares_source_url",
    ]
    if frame.loc[available, available_fields].isna().any().any():
        raise ValueError("Available Market Cap rows require value, price, and complete eligible share-fact provenance.")
    if frame.loc[available, "source_metric_ids"].astype(str).str.strip().eq("").any():
        raise ValueError("Available Market Cap rows require source metric lineage.")
    if frame.loc[available, "value"].map(lambda value: float(value) <= 0 or not math.isfinite(float(value))).any():
        raise ValueError("Available Market Cap values must be finite and positive.")
    if frame.loc[available, "price"].map(lambda value: float(value) <= 0 or not math.isfinite(float(value))).any():
        raise ValueError("Available Market Cap prices must be finite and positive.")
    if frame.loc[available, "shares_outstanding"].map(lambda value: float(value) <= 0 or not math.isfinite(float(value))).any():
        raise ValueError("Available share counts must be finite and positive.")
    unavailable = ~available
    if frame.loc[unavailable, "value"].notna().any():
        raise ValueError("Unavailable Market Cap rows must not contain a numeric value.")
    if (frame.loc[available, "value"] != frame.loc[available, "price"] * frame.loc[available, "shares_outstanding"]).any():
        raise ValueError("Market Cap Gold value must equal exact price × eligible shares.")
    if (frame.loc[available, "shares_reference_date"] > frame.loc[available, "reference_date"]).any():
        raise ValueError("Market Cap Gold cannot use a future share-count reference date.")
    if (frame.loc[available, "shares_filed_at"] > frame.loc[available, "reference_date"]).any():
        raise ValueError("Market Cap Gold cannot use a future-filed share-count fact.")
    for column in ("market_source_content_sha256",):
        present = frame[column].dropna().astype(str)
        if not present.str.fullmatch(r"[0-9a-fA-F]{64}").all():
            raise ValueError(f"Market Cap Gold {column} must be SHA-256 when present.")
    return frame.sort_values(list(MARKET_CAP_KEY), kind="mergesort").reset_index(drop=True)


def validate_market_cap_gold(rows: pd.DataFrame) -> None:
    _prepare(rows)


def merge_market_cap_gold(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Idempotently merge derived rows; conflicting values for one date fail."""
    fresh = _prepare(incoming)
    if existing.empty:
        return fresh
    prior = _prepare(existing)
    combined = pd.concat([prior, fresh], ignore_index=True)
    retained: list[pd.Series] = []
    for _, group in combined.groupby(list(MARKET_CAP_KEY), sort=True, dropna=False):
        first = group.iloc[0]
        for _, candidate in group.iloc[1:].iterrows():
            for column in _ANALYTICAL_FIELDS:
                left, right = first[column], candidate[column]
                if pd.isna(left) and pd.isna(right):
                    continue
                if pd.isna(left) != pd.isna(right) or left != right:
                    raise ValueError("Conflicting Market Cap Gold result for ticker + reference_date.")
        # Retrieval timestamp is technical provenance; keep the stable earliest value.
        retained.append(group.sort_values("market_retrieved_at", kind="mergesort").iloc[0])
    return _prepare(pd.DataFrame(retained, columns=list(MARKET_CAP_GOLD_COLUMNS)))


def write_market_cap_gold(
    rows: pd.DataFrame,
    *,
    path: Path = DEFAULT_MARKET_CAP_PATH,
) -> tuple[Path, Path]:
    output = Path(path)
    incoming = _prepare(rows)
    metadata_path = output.with_suffix(output.suffix + ".metadata.json")
    existing = read_market_cap_gold(output) if output.exists() else pd.DataFrame(columns=list(MARKET_CAP_GOLD_COLUMNS))
    merged = merge_market_cap_gold(existing, incoming)
    if output.exists() and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_valid = (
                metadata.get("dataset") == "market_capitalization"
                and metadata.get("schema_version") == SCHEMA_VERSION
                and metadata.get("row_count") == len(existing)
                and isinstance(metadata.get("generated_at"), str)
                and bool(metadata["generated_at"].strip())
            )
        except (OSError, json.JSONDecodeError, AttributeError, KeyError):
            metadata_valid = False
        if metadata_valid and merged.equals(existing):
            return output, metadata_path
    table = pa.Table.from_pandas(merged, schema=MARKET_CAP_SCHEMA, preserve_index=False, safe=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp")
    os.close(descriptor)
    temporary = Path(name)
    try:
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_descriptor, metadata_name = tempfile.mkstemp(dir=metadata_path.parent, prefix=f".{metadata_path.name}.", suffix=".tmp")
    metadata_temp = Path(metadata_name)
    try:
        with os.fdopen(metadata_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({
                "dataset": "market_capitalization",
                "schema_version": SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "row_count": table.num_rows,
                "parquet_file": output.name,
                "identity_key": "ticker + reference_date",
                "methodology_versions": sorted(set(merged.methodology_version.astype(str))),
            }, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(metadata_temp, metadata_path)
    except Exception:
        metadata_temp.unlink(missing_ok=True)
        raise
    return output, metadata_path


def read_market_cap_gold(path: Path = DEFAULT_MARKET_CAP_PATH) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        return pd.DataFrame(columns=list(MARKET_CAP_GOLD_COLUMNS))
    table = pq.read_table(source)
    if table.schema != MARKET_CAP_SCHEMA:
        raise ValueError("Market Cap Gold Parquet schema mismatch.")
    return _prepare(table.to_pandas())
