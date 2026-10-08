"""Atomic, replay-safe Parquet storage for SWOT Gold classifications."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import GOLD_DIR
from meli_intelligence.strategy.swot import SWOT_COLUMNS, validate_swot

DEFAULT_SWOT_PATH = GOLD_DIR / "strategy" / "swot.parquet"
SWOT_SCHEMA_VERSION = "1"
_SCHEMA = pa.schema(
    [
        pa.field(
            column,
            pa.date32() if column in {"reference_date", "period_start", "period_end"}
            else pa.bool_() if column == "is_interpretation"
            else pa.string(),
            nullable=column not in {
                "swot_id", "swot_category", "business_domain", "claim", "assessment",
                "classification_rationale", "source_evidence_ids", "source_evidence_types",
                "source_metric_ids", "source_pestel_ids", "source_pestel_dimensions", "source",
                "methodology_version", "definition_context", "scope", "is_interpretation",
            },
        )
        for column in SWOT_COLUMNS
    ],
    metadata={b"schema_version": b"1", b"dataset": b"swot"},
)


def _fingerprint(row) -> str:
    normalized = {
        key: value.isoformat() if hasattr(value, "isoformat")
        else None if pd.isna(value)
        else value.item() if hasattr(value, "item")
        else value
        for key, value in row.items()
    }
    return json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False)


def _merge(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    old = validate_swot(existing) if not existing.empty else pd.DataFrame(columns=SWOT_COLUMNS)
    new = validate_swot(incoming)
    if old.swot_id.duplicated(keep=False).any():
        raise ValueError("Stored SWOT IDs are not unique.")
    old_by_id = {str(row.swot_id): _fingerprint(row.to_dict()) for _, row in old.iterrows()}
    new_by_id: dict[str, str] = {}
    for _, row in new.iterrows():
        key = str(row.swot_id)
        fingerprint = _fingerprint(row.to_dict())
        if key in new_by_id and new_by_id[key] != fingerprint:
            raise ValueError(f"Incoming SWOT identity conflict for swot_id={key!r}.")
        new_by_id[key] = fingerprint
    for key in set(old_by_id) & set(new_by_id):
        if old_by_id[key] != new_by_id[key]:
            raise ValueError(f"SWOT identity conflict for swot_id={key!r}.")
    fresh = new.loc[~new.swot_id.astype(str).isin(old_by_id)]
    return validate_swot(pd.concat([old, fresh], ignore_index=True))


def write_swot(frame: pd.DataFrame, path: str | Path = DEFAULT_SWOT_PATH) -> Path:
    incoming = validate_swot(frame)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = pq.read_table(destination).to_pandas() if destination.exists() else pd.DataFrame(columns=SWOT_COLUMNS)
    merged = _merge(existing, incoming)
    fd, temp_path = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    os.close(fd)
    try:
        table = pa.Table.from_pandas(merged[SWOT_COLUMNS], schema=_SCHEMA, preserve_index=False, safe=True)
        pq.write_table(table, temp_path, compression="zstd")
        os.replace(temp_path, destination)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return destination
