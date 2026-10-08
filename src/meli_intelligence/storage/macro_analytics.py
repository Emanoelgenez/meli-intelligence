"""Typed, revision-safe Gold persistence for Macro Analytics and Evidence."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import GOLD_DIR


MACRO_ANALYTICS_SCHEMA_VERSION = "1"
DEFAULT_MACRO_ANALYTICS_PATH = GOLD_DIR / "macro" / "macro_analytics.parquet"
DEFAULT_MACRO_EVIDENCE_PATH = GOLD_DIR / "macro" / "macro_evidence.parquet"
MACRO_ANALYTICS_SCHEMA = pa.schema([
    pa.field("metric_id", pa.string(), nullable=False),
    pa.field("reference_date", pa.date32(), nullable=False),
    pa.field("value", pa.float64(), nullable=False),
    pa.field("unit", pa.string(), nullable=False),
    pa.field("frequency", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("source_metric_id", pa.string(), nullable=False),
    pa.field("analytics_kind", pa.string(), nullable=False),
    pa.field("definition_context", pa.string(), nullable=False),
    pa.field("previous_reference_date", pa.date32(), nullable=True),
    pa.field("previous_value", pa.float64(), nullable=True),
    pa.field("source_reference_date", pa.date32(), nullable=True),
    pa.field("direction_flag_id", pa.string(), nullable=True),
    pa.field("direction_value", pa.string(), nullable=True),
])
MACRO_EVIDENCE_SCHEMA = pa.schema([
    pa.field("evidence_id", pa.string(), nullable=False),
    pa.field("evidence_type", pa.string(), nullable=False),
    pa.field("business_domain", pa.string(), nullable=False),
    pa.field("metric_id", pa.string(), nullable=False),
    pa.field("reference_date", pa.date32(), nullable=False),
    pa.field("claim", pa.string(), nullable=False),
    pa.field("claim_kind", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("source_metric_id", pa.string(), nullable=False),
    pa.field("is_interpretation", pa.bool_(), nullable=False),
    pa.field("definition_context", pa.string(), nullable=False),
    pa.field("analytics_kind", pa.string(), nullable=False),
    pa.field("methodology_version", pa.string(), nullable=False),
])


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_bytes(path, encoded)


def _validate_analytics(frame: pd.DataFrame) -> None:
    missing = set(MACRO_ANALYTICS_SCHEMA.names).difference(frame.columns)
    if missing:
        raise ValueError(f"Macro Analytics missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Macro Analytics cannot be empty.")
    required = [name for name in MACRO_ANALYTICS_SCHEMA.names if name not in {
        "previous_reference_date", "previous_value", "source_reference_date",
        "direction_flag_id", "direction_value",
    }]
    if frame[required].isna().any().any():
        raise ValueError("Macro Analytics required fields cannot be null.")
    if frame.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate Macro Analytics economic key.")
    if not pd.api.types.is_numeric_dtype(frame.value) or not frame.value.map(
        lambda value: math.isfinite(float(value))
    ).all():
        raise ValueError("Macro Analytics values must be finite numeric values.")
    if (
        frame.source.astype(str).str.strip().eq("").any()
        or frame.source_metric_id.astype(str).str.strip().eq("").any()
        or frame.definition_context.astype(str).str.strip().eq("").any()
    ):
        raise ValueError("Macro Analytics lineage and definition context cannot be empty.")
    flag_pairs = frame[["direction_flag_id", "direction_value"]].isna()
    if (flag_pairs.direction_flag_id != flag_pairs.direction_value).any():
        raise ValueError("Macro direction flag ID and value must be set together.")
    allowed_flags = {
        "rising", "falling", "unchanged", "accelerating", "decelerating",
        "appreciating_brl", "depreciating_brl", "expanding", "contracting",
    }
    if not set(frame.direction_value.dropna().astype(str)).issubset(allowed_flags):
        raise ValueError("Macro Analytics contains an unsupported direction flag.")


def _prepare(frame: pd.DataFrame, schema: pa.Schema) -> pd.DataFrame:
    prepared = frame[schema.names].copy()
    for column in ("reference_date", "previous_reference_date", "source_reference_date"):
        if column in prepared:
            prepared[column] = pd.to_datetime(prepared[column], errors="raise").dt.date
    if "value" in prepared:
        prepared["value"] = prepared["value"].astype("float64")
    if "previous_value" in prepared:
        prepared["previous_value"] = pd.to_numeric(prepared.previous_value, errors="raise").astype("float64")
    return prepared


def _metadata_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".metadata.json")


def _read(path: Path, schema: pa.Schema) -> pd.DataFrame:
    table = pq.read_table(path)
    if table.schema != schema:
        raise ValueError(f"Gold Parquet schema mismatch: {path}")
    return table.to_pandas()


def _merge_analytics(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    _validate_analytics(incoming)
    if existing.empty:
        return incoming.copy()
    _validate_analytics(existing)
    left, right = existing.copy(), incoming.copy()
    left["reference_date"] = pd.to_datetime(left.reference_date).dt.date
    right["reference_date"] = pd.to_datetime(right.reference_date).dt.date
    overlap = left.merge(right, on=["metric_id", "reference_date"], suffixes=("_old", "_new"), validate="one_to_one")
    conflicts = overlap.loc[overlap.value_old != overlap.value_new]
    if not conflicts.empty:
        row = conflicts.iloc[0]
        raise ValueError(
            "Macro Analytics revision conflict for "
            f"metric_id={row.metric_id!r}, reference_date={row.reference_date!r}: "
            f"existing value={float(row.value_old)!r}, incoming value={float(row.value_new)!r}."
        )
    fresh = right.merge(left[["metric_id", "reference_date"]], on=["metric_id", "reference_date"], how="left", indicator=True)
    fresh = fresh.loc[fresh._merge == "left_only", right.columns]
    return pd.concat([left, fresh], ignore_index=True).sort_values(["metric_id", "reference_date"]).reset_index(drop=True)


def _merge_evidence(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    missing = set(MACRO_EVIDENCE_SCHEMA.names).difference(incoming.columns)
    if missing:
        raise ValueError(f"Macro Evidence missing columns: {sorted(missing)}")
    if incoming.empty:
        raise ValueError("Macro Evidence cannot be empty.")
    if incoming[list(MACRO_EVIDENCE_SCHEMA.names)].isna().any().any():
        raise ValueError("Macro Evidence required fields cannot be null.")
    if incoming.evidence_id.duplicated(keep=False).any():
        raise ValueError("Duplicate Macro Evidence IDs.")
    if (
        not incoming.is_interpretation.eq(False).all()
        or not incoming.evidence_type.eq("OBSERVATION").all()
        or not incoming.business_domain.eq("Macro").all()
    ):
        raise ValueError("Macro Evidence Gold accepts OBSERVATION records only.")
    if existing.empty:
        return incoming.copy()
    if existing.evidence_id.duplicated(keep=False).any():
        raise ValueError("Stored Macro Evidence contains duplicate IDs.")
    overlap = existing.merge(incoming, on="evidence_id", suffixes=("_old", "_new"), validate="one_to_one")
    columns = [column for column in MACRO_EVIDENCE_SCHEMA.names if column != "evidence_id"]
    for _, row in overlap.iterrows():
        if any(row[f"{column}_old"] != row[f"{column}_new"] for column in columns):
            raise ValueError(f"Macro Evidence identity conflict for evidence_id={row.evidence_id!r}.")
    fresh = incoming.loc[~incoming.evidence_id.isin(existing.evidence_id)]
    return pd.concat([existing, fresh], ignore_index=True).sort_values(["reference_date", "evidence_id"]).reset_index(drop=True)


def _write(
    frame: pd.DataFrame,
    *,
    path: Path,
    schema: pa.Schema,
    dataset: str,
    identity_column: str,
) -> tuple[Path, Path]:
    path = Path(path)
    prepared = _prepare(frame, schema)
    table = pa.Table.from_pandas(prepared, schema=schema, preserve_index=False, safe=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(descriptor)
    temporary = Path(name)
    try:
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    metadata_path = _metadata_path(path)
    metadata = {
        "dataset": dataset,
        "schema_version": MACRO_ANALYTICS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": table.num_rows,
        "parquet_file": path.name,
        "identity_column": identity_column,
        "source_metric_ids": sorted(set(prepared.get("source_metric_id", pd.Series(dtype=str)).dropna().astype(str))),
        "sources": sorted(set(prepared.get("source", pd.Series(dtype=str)).dropna().astype(str))),
        "metric_ids": sorted(set(prepared.get("metric_id", pd.Series(dtype=str)).dropna().astype(str))),
    }
    _atomic_json(metadata_path, metadata)
    return path, metadata_path


def write_macro_analytics(
    frame: pd.DataFrame,
    *,
    path: Path = DEFAULT_MACRO_ANALYTICS_PATH,
) -> tuple[Path, Path]:
    """Idempotently merge and atomically persist derived analytics in Gold."""
    path = Path(path)
    _validate_analytics(frame)
    merged = _merge_analytics(_read(path, MACRO_ANALYTICS_SCHEMA), frame) if path.exists() else frame.copy()
    return _write(merged, path=path, schema=MACRO_ANALYTICS_SCHEMA, dataset="macro_analytics", identity_column="metric_id + reference_date")


def write_macro_evidence(
    frame: pd.DataFrame,
    *,
    path: Path = DEFAULT_MACRO_EVIDENCE_PATH,
) -> tuple[Path, Path]:
    """Idempotently merge deterministic observations and persist Gold Parquet."""
    path = Path(path)
    existing = _read(path, MACRO_EVIDENCE_SCHEMA) if path.exists() else pd.DataFrame(columns=MACRO_EVIDENCE_SCHEMA.names)
    merged = _merge_evidence(existing, frame)
    return _write(merged, path=path, schema=MACRO_EVIDENCE_SCHEMA, dataset="macro_evidence", identity_column="evidence_id")


def read_macro_analytics(path: Path = DEFAULT_MACRO_ANALYTICS_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(f"Macro Analytics Gold Parquet not found: {path}")
    return _read(Path(path), MACRO_ANALYTICS_SCHEMA)


def read_macro_evidence(path: Path = DEFAULT_MACRO_EVIDENCE_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(f"Macro Evidence Gold Parquet not found: {path}")
    return _read(Path(path), MACRO_EVIDENCE_SCHEMA)
