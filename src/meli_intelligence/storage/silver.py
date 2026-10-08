"""Typed Silver persistence for canonical financial facts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.config.settings import SILVER_DIR


SILVER_SCHEMA_VERSION = "1"

DEFAULT_FINANCIAL_FACTS_PATH = (
    SILVER_DIR
    / "sec"
    / "financial_facts.parquet"
)


FINANCIAL_FACTS_SCHEMA = pa.schema(
    [
        pa.field("entity_cik", pa.string(), nullable=False),
        pa.field("entity_name", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("metric_id", pa.string(), nullable=False),
        pa.field("taxonomy", pa.string(), nullable=False),
        pa.field("concept", pa.string(), nullable=False),
        pa.field("unit", pa.string(), nullable=False),
        pa.field("value", pa.int64(), nullable=False),
        pa.field("period_start", pa.date32(), nullable=True),
        pa.field("period_end", pa.date32(), nullable=False),
        pa.field("reference_year", pa.int32(), nullable=False),
        pa.field("period_type", pa.string(), nullable=False),
        pa.field("period_label", pa.string(), nullable=False),
        pa.field("form", pa.string(), nullable=False),
        pa.field("filed_at", pa.date32(), nullable=False),
        pa.field("accession_number", pa.string(), nullable=False),
        pa.field("frame", pa.string(), nullable=True),
        pa.field("source_fy", pa.int32(), nullable=True),
        pa.field("source_fp", pa.string(), nullable=True),
        pa.field("occurrences", pa.int32(), nullable=False),
        pa.field(
            "first_reported_value",
            pa.int64(),
            nullable=True,
        ),
        pa.field(
            "first_filed_at",
            pa.date32(),
            nullable=True,
        ),
        pa.field(
            "first_accession_number",
            pa.string(),
            nullable=True,
        ),
        pa.field(
            "has_value_change",
            pa.bool_(),
            nullable=False,
        ),
        pa.field(
            "value_change",
            pa.int64(),
            nullable=True,
        ),
        pa.field(
            "is_derived",
            pa.bool_(),
            nullable=False,
        ),
    ]
)


REQUIRED_FIELDS = {
    "metric_id",
    "taxonomy",
    "concept",
    "unit",
    "value",
    "period_end",
    "reference_year",
    "period_type",
    "period_label",
    "form",
    "filed_at",
    "accession_number",
}


ALLOWED_PERIOD_TYPES = {
    "INSTANT",
    "QUARTER",
    "YTD",
    "FY",
}


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def validate_financial_facts(
    rows: list[dict[str, Any]],
) -> None:
    """Validate canonical facts before writing Silver."""
    if not rows:
        raise ValueError(
            "Financial facts dataset cannot be empty."
        )

    seen_keys: set[tuple[Any, ...]] = set()

    for index, row in enumerate(rows):
        missing = [
            field
            for field in REQUIRED_FIELDS
            if row.get(field) is None
        ]

        if missing:
            raise ValueError(
                f"Row {index} has null required fields: "
                f"{sorted(missing)}"
            )

        if row["period_type"] not in ALLOWED_PERIOD_TYPES:
            raise ValueError(
                f"Row {index} has invalid period_type: "
                f"{row['period_type']}"
            )

        if row["unit"] != "USD":
            raise ValueError(
                f"Row {index} has unexpected unit: "
                f"{row['unit']}"
            )

        period_start = row.get("period_start")

        if (
            row["period_type"] == "INSTANT"
            and period_start is not None
        ):
            raise ValueError(
                f"Row {index}: INSTANT must not have period_start."
            )

        if (
            row["period_type"] != "INSTANT"
            and period_start is None
        ):
            raise ValueError(
                f"Row {index}: duration fact requires period_start."
            )

        key = (
            row["metric_id"],
            row["unit"],
            period_start,
            row["period_end"],
        )

        if key in seen_keys:
            raise ValueError(
                "Duplicate canonical economic fact detected: "
                f"{key}"
            )

        seen_keys.add(key)


def _prepare_rows(
    rows: list[dict[str, Any]],
    *,
    entity_cik: str,
    entity_name: str,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []

    for row in rows:
        prepared.append(
            {
                "entity_cik": entity_cik,
                "entity_name": entity_name,
                "source": "SEC EDGAR Company Facts API",
                "metric_id": row["metric_id"],
                "taxonomy": row["taxonomy"],
                "concept": row["concept"],
                "unit": row["unit"],
                "value": row["value"],
                "period_start": _parse_date(
                    row.get("period_start")
                ),
                "period_end": _parse_date(
                    row["period_end"]
                ),
                "reference_year": row["reference_year"],
                "period_type": row["period_type"],
                "period_label": row["period_label"],
                "form": row["form"],
                "filed_at": _parse_date(
                    row["filed_at"]
                ),
                "accession_number": row[
                    "accession_number"
                ],
                "frame": row.get("frame"),
                "source_fy": row.get("source_fy"),
                "source_fp": row.get("source_fp"),
                "occurrences": row["occurrences"],
                "first_reported_value": row.get(
                    "first_reported_value"
                ),
                "first_filed_at": _parse_date(
                    row.get("first_filed_at")
                ),
                "first_accession_number": row.get(
                    "first_accession_number"
                ),
                "has_value_change": row[
                    "has_value_change"
                ],
                "value_change": row.get(
                    "value_change"
                ),
                "is_derived": row["is_derived"],
            }
        )

    return prepared


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
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

    temp_path = Path(temp_name)

    try:
        with os.fdopen(
            descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as file:
            json.dump(
                payload,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        os.replace(temp_path, path)

    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def write_financial_facts_parquet(
    rows: list[dict[str, Any]],
    *,
    entity_cik: str,
    entity_name: str,
    output_path: Path = DEFAULT_FINANCIAL_FACTS_PATH,
    source_bronze_path: Path | None = None,
) -> tuple[Path, Path]:
    """Validate and persist financial facts as typed Parquet."""
    validate_financial_facts(rows)

    output_path = Path(output_path)

    prepared = _prepare_rows(
        rows,
        entity_cik=entity_cik,
        entity_name=entity_name,
    )

    dataframe = pd.DataFrame(prepared)

    table = pa.Table.from_pandas(
        dataframe,
        schema=FINANCIAL_FACTS_SCHEMA,
        preserve_index=False,
        safe=True,
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temp_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )

    os.close(descriptor)

    temp_path = Path(temp_name)

    try:
        pq.write_table(
            table,
            temp_path,
            compression="zstd",
        )

        os.replace(
            temp_path,
            output_path,
        )

    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    metadata_path = output_path.with_suffix(
        ".metadata.json"
    )

    metadata: dict[str, Any] = {
        "dataset": "sec_financial_facts",
        "schema_version": SILVER_SCHEMA_VERSION,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "row_count": table.num_rows,
        "entity_cik": entity_cik,
        "entity_name": entity_name,
        "source": "SEC EDGAR Company Facts API",
        "parquet_file": output_path.name,
    }

    if source_bronze_path is not None:
        source_path = Path(source_bronze_path)

        metadata["source_bronze_file"] = (
            source_path.name
        )

        metadata["source_bronze_sha256"] = (
            _sha256(source_path)
        )

    _write_json_atomic(
        metadata_path,
        metadata,
    )

    return output_path, metadata_path