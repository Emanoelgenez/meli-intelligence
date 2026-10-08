"""Typed Silver storage for extended KPIs and evidence facts."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import SILVER_DIR


EXTENDED_SCHEMA_VERSION = "1"

EXTENDED_KPI_PATH = (
    SILVER_DIR
    / "sec"
    / "extended_operational_kpis.parquet"
)

EVIDENCE_PATH = (
    SILVER_DIR
    / "sec"
    / "evidence_facts.parquet"
)


EXTENDED_SCHEMA = pa.schema(
    [
        pa.field("entity_cik", pa.string(), nullable=False),
        pa.field("entity_name", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("metric_id", pa.string(), nullable=False),
        pa.field("scope", pa.string(), nullable=False),
        pa.field("reported_value", pa.float64(), nullable=False),
        pa.field("reported_scale", pa.string(), nullable=False),
        pa.field("value", pa.float64(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("value_qualifier", pa.string(), nullable=False),
        pa.field("period_start", pa.date32(), nullable=True),
        pa.field("period_end", pa.date32(), nullable=False),
        pa.field("reference_year", pa.int32(), nullable=False),
        pa.field("period_type", pa.string(), nullable=False),
        pa.field("period_label", pa.string(), nullable=False),
        pa.field("definition_version", pa.string(), nullable=False),
        pa.field("source_text", pa.string(), nullable=False),
        pa.field("filing_date", pa.date32(), nullable=False),
        pa.field("accession_number", pa.string(), nullable=False),
        pa.field("source_url", pa.string(), nullable=False),
        pa.field("source_bronze_file", pa.string(), nullable=False),
        pa.field("source_content_sha256", pa.string(), nullable=False),
    ]
)


EVIDENCE_SCHEMA = pa.schema(
    [
        pa.field("entity_cik", pa.string(), nullable=False),
        pa.field("entity_name", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("evidence_id", pa.string(), nullable=False),
        pa.field("evidence_class", pa.string(), nullable=False),
        pa.field("evidence_type", pa.string(), nullable=False),
        pa.field("business_domain", pa.string(), nullable=False),
        pa.field("reference_period", pa.date32(), nullable=False),
        pa.field("reference_year", pa.int32(), nullable=False),
        pa.field("statement", pa.string(), nullable=False),
        pa.field("has_numeric_signal", pa.bool_(), nullable=False),
        pa.field("filing_date", pa.date32(), nullable=False),
        pa.field("accession_number", pa.string(), nullable=False),
        pa.field("source_url", pa.string(), nullable=False),
        pa.field("source_bronze_file", pa.string(), nullable=False),
        pa.field("source_content_sha256", pa.string(), nullable=False),
    ]
)


def _atomic_parquet(
    frame: pd.DataFrame,
    schema: pa.Schema,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )

    os.close(
        descriptor
    )

    temp_path = Path(
        temp_name
    )

    try:
        table = pa.Table.from_pandas(
            frame[
                schema.names
            ],
            schema=schema,
            preserve_index=False,
            safe=True,
        )

        pq.write_table(
            table,
            temp_path,
            compression="zstd",
        )

        os.replace(
            temp_path,
            path,
        )

    except Exception:
        temp_path.unlink(
            missing_ok=True
        )
        raise


def _metadata(
    path: Path,
    *,
    dataset: str,
    row_count: int,
    source_files: list[dict],
) -> Path:
    metadata_path = Path(
        str(path)
        + ".metadata.json"
    )

    payload = {
        "dataset": dataset,
        "schema_version": (
            EXTENDED_SCHEMA_VERSION
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "row_count": row_count,
        "entity_cik": "0001099590",
        "entity_name": "MercadoLibre, Inc.",
        "source_file_count": len(
            source_files
        ),
        "source_files": source_files,
        "parquet_file": path.name,
    }

    metadata_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return metadata_path


def write_extended_silver(
    facts: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    source_files: list[dict],
) -> tuple[Path, Path, Path, Path]:
    """Write extended KPI facts and narrative evidence."""
    if facts.empty:
        raise ValueError(
            "Extended KPI facts cannot be empty."
        )

    if evidence.empty:
        raise ValueError(
            "Evidence facts cannot be empty."
        )

    fact_key = [
        "metric_id",
        "scope",
        "period_end",
        "definition_version",
    ]

    if facts.duplicated(
        subset=fact_key,
        keep=False,
    ).any():
        raise ValueError(
            "Duplicate extended KPI facts."
        )

    if evidence[
        "evidence_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate evidence IDs."
        )

    facts = facts.copy()
    evidence = evidence.copy()

    for column in [
        "period_start",
        "period_end",
        "filing_date",
    ]:
        facts[column] = pd.to_datetime(
            facts[column]
        ).dt.date

    facts["reference_year"] = (
        facts["reference_year"]
        .astype("int32")
    )

    for column in [
        "reference_period",
        "filing_date",
    ]:
        evidence[column] = pd.to_datetime(
            evidence[column]
        ).dt.date

    evidence["reference_year"] = (
        evidence["reference_year"]
        .astype("int32")
    )

    evidence[
        "has_numeric_signal"
    ] = evidence[
        "has_numeric_signal"
    ].astype(bool)

    _atomic_parquet(
        facts,
        EXTENDED_SCHEMA,
        EXTENDED_KPI_PATH,
    )

    _atomic_parquet(
        evidence,
        EVIDENCE_SCHEMA,
        EVIDENCE_PATH,
    )

    fact_metadata = _metadata(
        EXTENDED_KPI_PATH,
        dataset="extended_operational_kpis",
        row_count=len(facts),
        source_files=source_files,
    )

    evidence_metadata = _metadata(
        EVIDENCE_PATH,
        dataset="evidence_facts",
        row_count=len(evidence),
        source_files=source_files,
    )

    return (
        EXTENDED_KPI_PATH,
        fact_metadata,
        EVIDENCE_PATH,
        evidence_metadata,
    )