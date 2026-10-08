"""Typed Silver storage for authoritative SEC shares-outstanding facts."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import SILVER_DIR
from meli_intelligence.analytics.market_cap import (
    ENTITY,
    SEC_CONCEPT,
    SEC_METRIC_ID,
    SEC_SOURCE_LABELS,
    SEC_TAXONOMY,
)

SCHEMA_VERSION = "1"
DEFAULT_SHARES_OUTSTANDING_PATH = SILVER_DIR / "company" / "shares_outstanding.parquet"
SHARES_OUTSTANDING_COLUMNS = (
    "entity", "metric_id", "source_metric_id", "taxonomy", "concept",
    "reference_date", "value", "unit", "filed_at", "accession_number",
    "form", "source", "source_url", "source_bronze_file",
    "source_content_sha256",
)
SHARES_OUTSTANDING_SCHEMA = pa.schema([
    pa.field("entity", pa.string(), nullable=False),
    pa.field("metric_id", pa.string(), nullable=False),
    pa.field("source_metric_id", pa.string(), nullable=False),
    pa.field("taxonomy", pa.string(), nullable=False),
    pa.field("concept", pa.string(), nullable=False),
    pa.field("reference_date", pa.date32(), nullable=False),
    pa.field("value", pa.int64(), nullable=False),
    pa.field("unit", pa.string(), nullable=False),
    pa.field("filed_at", pa.date32(), nullable=False),
    pa.field("accession_number", pa.string(), nullable=False),
    pa.field("form", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("source_url", pa.string(), nullable=False),
    pa.field("source_bronze_file", pa.string(), nullable=True),
    pa.field("source_content_sha256", pa.string(), nullable=True),
])

# A filing revision of one economic reference date remains a separate fact.
SHARES_OUTSTANDING_KEY = (
    "entity", "taxonomy", "concept", "unit", "reference_date",
    "filed_at", "accession_number",
)
_MATERIAL_FIELDS = tuple(
    column for column in SHARES_OUTSTANDING_COLUMNS
    if column not in {"source_bronze_file", "source_content_sha256"}
)


def _frame(rows: pd.DataFrame | Iterable[dict[str, Any]]) -> pd.DataFrame:
    frame = rows.copy(deep=True) if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    missing = set(SHARES_OUTSTANDING_COLUMNS[:-2]).difference(frame.columns)
    if missing:
        raise ValueError(f"Shares Outstanding Silver is missing columns: {sorted(missing)}")
    for optional in SHARES_OUTSTANDING_COLUMNS[-2:]:
        if optional not in frame:
            frame[optional] = None
    return frame.loc[:, list(SHARES_OUTSTANDING_COLUMNS)].copy(deep=True)


def validate_shares_outstanding(rows: pd.DataFrame | Iterable[dict[str, Any]]) -> None:
    frame = _frame(rows)
    if frame.empty:
        raise ValueError("Shares Outstanding Silver cannot be empty.")
    required = list(SHARES_OUTSTANDING_COLUMNS[:-2])
    if frame[required].isna().any().any():
        raise ValueError("Shares Outstanding Silver required fields cannot be null.")
    if not frame.entity.astype(str).eq(ENTITY).all():
        raise ValueError("Shares Outstanding Silver supports MercadoLibre, Inc. only.")
    if not frame.metric_id.astype(str).eq("shares_outstanding").all():
        raise ValueError("Shares Outstanding Silver has an unsupported metric_id.")
    if not frame.source_metric_id.astype(str).eq(SEC_METRIC_ID).all():
        raise ValueError("Shares Outstanding Silver requires the authoritative SEC DEI metric.")
    if not frame.taxonomy.astype(str).eq(SEC_TAXONOMY).all() or not frame.concept.astype(str).eq(SEC_CONCEPT).all():
        raise ValueError("Shares Outstanding Silver requires dei:EntityCommonStockSharesOutstanding.")
    if not frame.unit.astype(str).str.casefold().eq("shares").all():
        raise ValueError("Shares Outstanding Silver unit must be shares.")
    if not frame.source.astype(str).isin(SEC_SOURCE_LABELS).all():
        raise ValueError("Shares Outstanding Silver source must be official SEC Company Facts.")
    if not frame.form.astype(str).isin({"10-K", "10-Q"}).all():
        raise ValueError("Shares Outstanding Silver accepts 10-K and 10-Q facts only.")
    if not frame.source_url.astype(str).str.startswith("https://data.sec.gov/api/xbrl/companyfacts/").all():
        raise ValueError("Shares Outstanding Silver requires official SEC Company Facts provenance.")
    for column in ("reference_date", "filed_at"):
        parsed = pd.to_datetime(frame[column], errors="coerce")
        if parsed.isna().any():
            raise ValueError(f"Shares Outstanding Silver {column} contains invalid dates.")
        frame[column] = parsed.dt.date
    values = pd.to_numeric(frame.value, errors="coerce")
    if values.isna().any() or not values.map(lambda value: math.isfinite(float(value)) and float(value) > 0 and float(value).is_integer()).all():
        raise ValueError("Shares Outstanding Silver values must be positive finite whole shares.")
    frame["value"] = values.astype("int64")
    if frame.accession_number.astype(str).str.strip().eq("").any():
        raise ValueError("Shares Outstanding Silver accession_number cannot be empty.")
    for _, group in frame.groupby(list(SHARES_OUTSTANDING_KEY), sort=True, dropna=False):
        first = group.iloc[0]
        for _, candidate in group.iloc[1:].iterrows():
            if any(candidate[column] != first[column] for column in _MATERIAL_FIELDS):
                raise ValueError("Conflicting shares-outstanding fact for identical SEC provenance key.")
    hashes = frame.source_content_sha256.dropna().astype(str)
    if not hashes.str.fullmatch(r"[0-9a-fA-F]{64}").all():
        raise ValueError("Shares Outstanding Silver source_content_sha256 must be SHA-256 when present.")


def _normalized(rows: pd.DataFrame | Iterable[dict[str, Any]]) -> pd.DataFrame:
    frame = _frame(rows)
    # Keep pandas representations canonical on both fresh and Parquet-read
    # frames so equality and replay decisions do not depend on inference.
    for field in SHARES_OUTSTANDING_SCHEMA:
        column = field.name
        if pa.types.is_string(field.type):
            normalized = frame[column].astype("object")
            frame[column] = normalized.where(pd.notna(normalized), None)
        elif pa.types.is_date32(field.type):
            frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
        elif pa.types.is_int64(field.type):
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
    validate_shares_outstanding(frame)
    frame = frame.sort_values(
        ["entity", "reference_date", "filed_at", "accession_number"],
        kind="mergesort",
    )
    # Replayed SEC observations may have multiple identical copies. Keep one
    # deterministically; provenance columns are optional and do not redefine
    # the authoritative fact's identity.
    frame["_bronze_sort"] = frame.source_bronze_file.fillna("").astype(str)
    frame["_hash_sort"] = frame.source_content_sha256.fillna("").astype(str)
    frame = frame.sort_values(
        [*SHARES_OUTSTANDING_KEY, "_bronze_sort", "_hash_sort"], kind="mergesort"
    ).drop_duplicates(list(SHARES_OUTSTANDING_KEY), keep="first")
    return frame.drop(columns=["_bronze_sort", "_hash_sort"]).sort_values(
        ["entity", "reference_date", "filed_at", "accession_number"], kind="mergesort"
    ).reset_index(drop=True)


def merge_shares_outstanding(
    existing: pd.DataFrame,
    incoming: pd.DataFrame | Iterable[dict[str, Any]],
) -> pd.DataFrame:
    """Merge SEC facts by filing provenance; exact replays dedupe, conflicts fail."""
    fresh = _normalized(incoming)
    if existing.empty:
        return fresh
    prior = _normalized(existing)
    combined = pd.concat([prior, fresh], ignore_index=True)
    kept: list[pd.Series] = []
    for _, group in combined.groupby(list(SHARES_OUTSTANDING_KEY), sort=True, dropna=False):
        reference = group.iloc[0]
        for _, candidate in group.iloc[1:].iterrows():
            if any(candidate[column] != reference[column] for column in _MATERIAL_FIELDS):
                raise ValueError("Conflicting shares-outstanding fact for identical SEC provenance key.")
        # Optional Bronze provenance can differ on replay; choose a stable row.
        ranked = group.assign(
            _bronze=group.source_bronze_file.fillna("").astype(str),
            _hash=group.source_content_sha256.fillna("").astype(str),
        ).sort_values(["_bronze", "_hash"], kind="mergesort")
        kept.append(ranked.iloc[0].drop(labels=["_bronze", "_hash"]))
    result = pd.DataFrame(kept, columns=list(SHARES_OUTSTANDING_COLUMNS))
    return _normalized(result)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_shares_outstanding(
    rows: pd.DataFrame | Iterable[dict[str, Any]],
    *,
    path: Path = DEFAULT_SHARES_OUTSTANDING_PATH,
) -> tuple[Path, Path]:
    """Idempotently merge and atomically write SEC shares facts as Silver Parquet."""
    output = Path(path)
    incoming = _normalized(rows)
    metadata_path = output.with_suffix(output.suffix + ".metadata.json")
    existing = read_shares_outstanding(output) if output.exists() else pd.DataFrame(columns=list(SHARES_OUTSTANDING_COLUMNS))
    merged = merge_shares_outstanding(existing, incoming) if output.exists() else incoming
    if output.exists() and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_valid = (
                metadata.get("dataset") == "shares_outstanding"
                and metadata.get("schema_version") == SCHEMA_VERSION
                and metadata.get("row_count") == len(existing)
                and isinstance(metadata.get("generated_at"), str)
                and bool(metadata["generated_at"].strip())
            )
        except (OSError, json.JSONDecodeError, AttributeError, KeyError):
            metadata_valid = False
        if metadata_valid and merged.equals(existing):
            return output, metadata_path
    prepared = merged.loc[:, list(SHARES_OUTSTANDING_COLUMNS)]
    table = pa.Table.from_pandas(prepared, schema=SHARES_OUTSTANDING_SCHEMA, preserve_index=False, safe=True)
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
    _atomic_json(metadata_path, {
        "dataset": "shares_outstanding", "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": table.num_rows, "parquet_file": output.name,
        "identity_key": "entity + taxonomy + concept + unit + reference_date + filed_at + accession_number",
        "source_metric_ids": sorted(set(prepared.source_metric_id.astype(str))),
    })
    return output, metadata_path


def read_shares_outstanding(path: Path = DEFAULT_SHARES_OUTSTANDING_PATH) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=list(SHARES_OUTSTANDING_COLUMNS))
    table = pq.read_table(path)
    if table.schema != SHARES_OUTSTANDING_SCHEMA:
        raise ValueError("Shares Outstanding Silver schema mismatch.")
    return _normalized(table.to_pandas())
