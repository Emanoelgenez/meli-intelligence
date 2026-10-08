"""Typed Parquet storage for generic macroeconomic indicators."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import SILVER_DIR


MACRO_SCHEMA_VERSION = "2"
DEFAULT_MACRO_INDICATORS_PATH = (
    SILVER_DIR / "macro" / "macro_indicators.parquet"
)
MACRO_INDICATORS_SCHEMA = pa.schema(
    [
        pa.field("metric_id", pa.string(), nullable=False),
        pa.field("source_series_id", pa.string(), nullable=False),
        pa.field("reference_date", pa.date32(), nullable=False),
        pa.field("value", pa.float64(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("frequency", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("source_url", pa.string(), nullable=False),
        pa.field("retrieved_at", pa.string(), nullable=False),
        pa.field("ingestion_version", pa.string(), nullable=False),
    ]
)
MACRO_KEY = ["metric_id", "reference_date"]


def validate_macro_indicators(frame: pd.DataFrame) -> None:
    """Validate generic macro Silver rows and economic-key uniqueness."""
    missing = set(MACRO_INDICATORS_SCHEMA.names).difference(frame.columns)
    if missing:
        raise ValueError(f"Macro Silver is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Macro Silver dataset cannot be empty.")
    if frame[MACRO_INDICATORS_SCHEMA.names].isna().any().any():
        raise ValueError("Macro Silver required fields cannot be null.")
    if not frame["source_series_id"].map(lambda value: isinstance(value, str) and bool(value)).all():
        raise ValueError("Macro Silver source_series_id must be a non-empty string.")
    if frame.duplicated(MACRO_KEY, keep=False).any():
        raise ValueError("Duplicate macro economic key metric_id + reference_date.")
    if not pd.api.types.is_numeric_dtype(frame["value"]):
        raise ValueError("Macro Silver value must be numeric.")
    if not frame["value"].map(lambda value: math.isfinite(float(value))).all():
        raise ValueError("Macro Silver value must be finite.")


def merge_macro_indicators(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    """Add new economic keys, preserving prior lineage on identical repeats."""
    if existing.empty:
        result = incoming.copy()
        validate_macro_indicators(result)
        return result
    validate_macro_indicators(existing)
    validate_macro_indicators(incoming)
    prior = existing.copy()
    fresh = incoming.copy()
    prior["reference_date"] = pd.to_datetime(prior["reference_date"]).dt.date
    fresh["reference_date"] = pd.to_datetime(fresh["reference_date"]).dt.date
    overlapping = prior.merge(
        fresh,
        on=MACRO_KEY,
        how="inner",
        suffixes=("_existing", "_incoming"),
        validate="one_to_one",
    )
    if not overlapping.empty:
        conflicts = overlapping.loc[
            (overlapping["value_existing"] != overlapping["value_incoming"])
            | (overlapping["source_series_id_existing"] != overlapping["source_series_id_incoming"])
            | (overlapping["unit_existing"] != overlapping["unit_incoming"])
        ]
        if not conflicts.empty:
            conflict = conflicts.iloc[0]
            raise ValueError(
                "Incoming macro values conflict with stored economic key "
                f"metric_id={conflict['metric_id']!r}, "
                f"reference_date={conflict['reference_date']!r}: "
                f"existing value={float(conflict['value_existing'])!r}, "
                f"incoming value={float(conflict['value_incoming'])!r}."
            )
    incoming_only = fresh.merge(
        prior[MACRO_KEY], on=MACRO_KEY, how="left", indicator=True
    ).loc[lambda rows: rows["_merge"] == "left_only", fresh.columns]
    result = pd.concat([prior, incoming_only], ignore_index=True)
    validate_macro_indicators(result)
    return result.sort_values(MACRO_KEY).reset_index(drop=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def write_macro_indicators(
    frame: pd.DataFrame,
    *,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
    source_bronze_files: list[str] | None = None,
) -> tuple[Path, Path]:
    """Validate and atomically persist the generic macro Silver table."""
    output_path = Path(output_path)
    validate_macro_indicators(frame)
    prepared = frame[MACRO_INDICATORS_SCHEMA.names].copy()
    prepared["reference_date"] = pd.to_datetime(prepared["reference_date"]).dt.date
    prepared["source_series_id"] = prepared["source_series_id"].astype("string").astype(str)
    prepared["value"] = prepared["value"].astype("float64")
    table = pa.Table.from_pandas(
        prepared,
        schema=MACRO_INDICATORS_SCHEMA,
        preserve_index=False,
        safe=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent, prefix=f".{output_path.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        pq.write_table(table, temporary_path, compression="zstd")
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    metadata_path = output_path.with_suffix(".metadata.json")
    _atomic_json(
        metadata_path,
        {
            "dataset": "macro_indicators",
            "schema_version": MACRO_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "row_count": table.num_rows,
            "sources": sorted(set(prepared["source"].astype(str))),
            "parquet_file": output_path.name,
            "source_bronze_files": source_bronze_files or [],
        },
    )
    return output_path, metadata_path


def read_macro_indicators(path: Path = DEFAULT_MACRO_INDICATORS_PATH) -> pd.DataFrame:
    """Read macro Silver using the declared schema."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Macro Silver Parquet not found: {path}")
    table = pq.read_table(path)
    if table.schema != MACRO_INDICATORS_SCHEMA:
        # Read existing Sprint 3A BCB Parquet without losing its provenance.
        legacy = table.to_pandas()
        if "series_code" in legacy.columns and "source_series_id" not in legacy.columns:
            legacy["source_series_id"] = legacy["series_code"].map(
                lambda code: f"bcb_sgs:{int(code)}"
            )
            legacy = legacy.drop(columns=["series_code"])
            legacy = legacy[MACRO_INDICATORS_SCHEMA.names]
            validate_macro_indicators(legacy)
            return legacy
        raise ValueError("Macro Silver schema does not match the registered schema.")
    return table.to_pandas()
