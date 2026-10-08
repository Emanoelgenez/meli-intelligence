"""Atomic, replay-safe Parquet storage for Product Evidence Gold."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import GOLD_DIR
from meli_intelligence.product.evidence import PRODUCT_EVIDENCE_COLUMNS, validate_product_evidence

DEFAULT_PRODUCT_EVIDENCE_PATH = GOLD_DIR / "product" / "product_evidence.parquet"
PRODUCT_EVIDENCE_SCHEMA_VERSION = "1"
_DATE_COLUMNS = {"reference_date", "period_start", "period_end"}
_REQUIRED_COLUMNS = {
    "product_evidence_id", "product_evidence_type", "discovery_theme", "business_domain",
    "statement", "rationale", "source_evidence_ids", "source_interpretation_ids",
    "source_pestel_ids", "source_swot_ids", "source_hypothesis_ids", "source_metric_ids",
    "source", "methodology_version", "definition_context", "scope",
}
_SCHEMA = pa.schema(
    [
        pa.field(
            column,
            pa.date32() if column in _DATE_COLUMNS else pa.string(),
            nullable=column not in _REQUIRED_COLUMNS,
        )
        for column in PRODUCT_EVIDENCE_COLUMNS
    ],
    metadata={b"schema_version": b"1", b"dataset": b"product_evidence"},
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
    old = validate_product_evidence(existing) if not existing.empty else pd.DataFrame(columns=PRODUCT_EVIDENCE_COLUMNS)
    new = validate_product_evidence(incoming)
    if old.product_evidence_id.duplicated(keep=False).any():
        raise ValueError("Stored Product Evidence IDs are not unique.")
    old_by_id = {str(row.product_evidence_id): _fingerprint(row.to_dict()) for _, row in old.iterrows()}
    new_by_id: dict[str, str] = {}
    for _, row in new.iterrows():
        key = str(row.product_evidence_id)
        fingerprint = _fingerprint(row.to_dict())
        if key in new_by_id and new_by_id[key] != fingerprint:
            raise ValueError(f"Incoming Product Evidence identity conflict for product_evidence_id={key!r}.")
        new_by_id[key] = fingerprint
    for key in set(old_by_id) & set(new_by_id):
        if old_by_id[key] != new_by_id[key]:
            raise ValueError(f"Product Evidence identity conflict for product_evidence_id={key!r}.")
    fresh = new.loc[~new.product_evidence_id.astype(str).isin(old_by_id)]
    return validate_product_evidence(pd.concat([old, fresh], ignore_index=True))


def write_product_evidence(frame: pd.DataFrame, path: str | Path = DEFAULT_PRODUCT_EVIDENCE_PATH) -> Path:
    incoming = validate_product_evidence(frame)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = pq.read_table(destination).to_pandas() if destination.exists() else pd.DataFrame(columns=PRODUCT_EVIDENCE_COLUMNS)
    merged = _merge(existing, incoming)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
    os.close(fd)
    try:
        table = pa.Table.from_pandas(merged[PRODUCT_EVIDENCE_COLUMNS], schema=_SCHEMA, preserve_index=False, safe=True)
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, destination)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return destination
