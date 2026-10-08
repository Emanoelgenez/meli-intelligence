"""Silver storage for canonical MercadoLibre operational KPIs."""

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


SILVER_SCHEMA_VERSION = "1"

DEFAULT_OPERATIONAL_SILVER_PATH = (
    SILVER_DIR
    / "sec"
    / "operational_kpis.parquet"
)

CANONICAL_KEY = [
    "metric_id",
    "unit",
    "period_start",
    "period_end",
    "definition_version",
]


OPERATIONAL_SCHEMA = pa.schema(
    [
        pa.field(
            "entity_cik",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "entity_name",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "source",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "metric_id",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "source_label",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "reported_value",
            pa.float64(),
            nullable=False,
        ),
        pa.field(
            "reported_scale",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "value",
            pa.float64(),
            nullable=False,
        ),
        pa.field(
            "unit",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "period_start",
            pa.date32(),
            nullable=True,
        ),
        pa.field(
            "period_end",
            pa.date32(),
            nullable=False,
        ),
        pa.field(
            "reference_year",
            pa.int32(),
            nullable=False,
        ),
        pa.field(
            "period_type",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "period_label",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "definition_version",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "release_reference_period",
            pa.date32(),
            nullable=False,
        ),
        pa.field(
            "filing_date",
            pa.date32(),
            nullable=False,
        ),
        pa.field(
            "sec_report_date",
            pa.date32(),
            nullable=True,
        ),
        pa.field(
            "accession_number",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "source_url",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "source_bronze_file",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "source_content_sha256",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "source_is_comparative",
            pa.bool_(),
            nullable=False,
        ),
        pa.field(
            "occurrences",
            pa.int32(),
            nullable=False,
        ),
        pa.field(
            "first_reported_value",
            pa.float64(),
            nullable=False,
        ),
        pa.field(
            "first_filing_date",
            pa.date32(),
            nullable=False,
        ),
        pa.field(
            "first_accession_number",
            pa.string(),
            nullable=False,
        ),
        pa.field(
            "has_value_change",
            pa.bool_(),
            nullable=False,
        ),
        pa.field(
            "value_change",
            pa.float64(),
            nullable=False,
        ),
    ]
)


def canonicalize_operational_rows(
    rows: pd.DataFrame,
) -> pd.DataFrame:
    """Select latest filing presentation within one definition version."""
    if rows.empty:
        raise ValueError(
            "Operational source dataset is empty."
        )

    required = {
        "metric_id",
        "unit",
        "value",
        "period_start",
        "period_end",
        "definition_version",
        "filing_date",
        "accession_number",
        "is_comparative",
    }

    missing = required.difference(
        rows.columns
    )

    if missing:
        raise ValueError(
            "Operational rows missing columns: "
            f"{sorted(missing)}"
        )

    frame = rows.copy()

    for column in [
        "period_start",
        "period_end",
        "release_reference_period",
        "filing_date",
        "sec_report_date",
    ]:
        frame[column] = pd.to_datetime(
            frame[column]
        )

    frame = frame.sort_values(
        by=[
            "filing_date",
            "accession_number",
        ]
    ).reset_index(
        drop=True
    )

    output = []

    for _, group in frame.groupby(
        CANONICAL_KEY,
        dropna=False,
        sort=False,
    ):
        ordered = group.sort_values(
            by=[
                "filing_date",
                "accession_number",
            ]
        )

        first = ordered.iloc[0]
        latest = ordered.iloc[-1].copy()

        first_value = float(
            first["value"]
        )

        latest_value = float(
            latest["value"]
        )

        latest["source_is_comparative"] = bool(
            latest["is_comparative"]
        )

        latest["occurrences"] = int(
            len(ordered)
        )

        latest["first_reported_value"] = (
            first_value
        )

        latest["first_filing_date"] = (
            first["filing_date"]
        )

        latest[
            "first_accession_number"
        ] = first[
            "accession_number"
        ]

        latest["has_value_change"] = (
            latest_value != first_value
        )

        latest["value_change"] = (
            latest_value
            - first_value
        )

        output.append(
            latest
        )

    result = pd.DataFrame(
        output
    )

    return result.sort_values(
        by=[
            "metric_id",
            "period_end",
            "period_start",
            "definition_version",
        ],
        na_position="first",
    ).reset_index(
        drop=True
    )


def _validate(
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        raise ValueError(
            "Operational Silver dataset is empty."
        )

    allowed_period_types = {
        "INSTANT",
        "QUARTER",
        "YTD",
        "FY",
    }

    invalid = set(
        frame["period_type"]
    ).difference(
        allowed_period_types
    )

    if invalid:
        raise ValueError(
            "Invalid operational period types: "
            f"{sorted(invalid)}"
        )

    instant = (
        frame["period_type"]
        == "INSTANT"
    )

    if frame.loc[
        instant,
        "period_start",
    ].notna().any():
        raise ValueError(
            "INSTANT operational facts cannot "
            "have period_start."
        )

    if frame.loc[
        ~instant,
        "period_start",
    ].isna().any():
        raise ValueError(
            "Duration operational facts require "
            "period_start."
        )

    duplicates = frame.duplicated(
        subset=CANONICAL_KEY,
        keep=False,
    )

    if duplicates.any():
        raise ValueError(
            "Duplicate canonical operational facts."
        )

    if frame[
        "definition_version"
    ].isna().any():
        raise ValueError(
            "definition_version is required."
        )


def _prepare(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    prepared = frame.copy()

    date_columns = [
        "period_start",
        "period_end",
        "release_reference_period",
        "filing_date",
        "sec_report_date",
        "first_filing_date",
    ]

    for column in date_columns:
        prepared[column] = pd.to_datetime(
            prepared[column]
        ).dt.date

    prepared["reference_year"] = (
        prepared["reference_year"]
        .astype("int32")
    )

    prepared["occurrences"] = (
        prepared["occurrences"]
        .astype("int32")
    )

    prepared["reported_value"] = (
        prepared["reported_value"]
        .astype(float)
    )

    prepared["value"] = (
        prepared["value"]
        .astype(float)
    )

    prepared["first_reported_value"] = (
        prepared["first_reported_value"]
        .astype(float)
    )

    prepared["value_change"] = (
        prepared["value_change"]
        .astype(float)
    )

    prepared["source_is_comparative"] = (
        prepared["source_is_comparative"]
        .astype(bool)
    )

    prepared["has_value_change"] = (
        prepared["has_value_change"]
        .astype(bool)
    )

    return prepared


def _atomic_write_json(
    path: Path,
    payload: dict,
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

    temp_path = Path(
        temp_name
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
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

        os.replace(
            temp_path,
            path,
        )

    except Exception:
        temp_path.unlink(
            missing_ok=True
        )
        raise


def write_operational_kpis_silver(
    frame: pd.DataFrame,
    *,
    output_path: Path = DEFAULT_OPERATIONAL_SILVER_PATH,
    source_files: list[dict] | None = None,
) -> tuple[Path, Path]:
    """Write canonical operational facts to typed Parquet."""
    _validate(
        frame
    )

    prepared = _prepare(
        frame
    )

    table = pa.Table.from_pandas(
        prepared[
            OPERATIONAL_SCHEMA.names
        ],
        schema=OPERATIONAL_SCHEMA,
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

    os.close(
        descriptor
    )

    temp_path = Path(
        temp_name
    )

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
        temp_path.unlink(
            missing_ok=True
        )
        raise

    metadata_path = Path(
        str(output_path)
        + ".metadata.json"
    )

    metadata = {
        "dataset": "operational_kpis",
        "schema_version": (
            SILVER_SCHEMA_VERSION
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "row_count": len(
            prepared
        ),
        "entity_cik": (
            prepared.iloc[0][
                "entity_cik"
            ]
        ),
        "entity_name": (
            prepared.iloc[0][
                "entity_name"
            ]
        ),
        "source_file_count": len(
            source_files or []
        ),
        "source_files": (
            source_files or []
        ),
        "parquet_file": (
            output_path.name
        ),
    }

    _atomic_write_json(
        metadata_path,
        metadata,
    )

    return (
        output_path,
        metadata_path,
    )