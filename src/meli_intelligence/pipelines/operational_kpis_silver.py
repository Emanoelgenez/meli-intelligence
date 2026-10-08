"""Pipeline for canonical operational KPI Silver facts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.storage.operational_silver import (
    DEFAULT_OPERATIONAL_SILVER_PATH,
    canonicalize_operational_rows,
    write_operational_kpis_silver,
)
from meli_intelligence.transformations.operational_kpis import (
    parse_operational_release,
)


ENTITY_CIK = "0001099590"
ENTITY_NAME = "MercadoLibre, Inc."

DEFAULT_BRONZE_DIR = (
    BRONZE_DIR
    / "sec"
    / "operational_releases"
)


def build_operational_kpis_silver(
    *,
    bronze_dir: Path = DEFAULT_BRONZE_DIR,
    output_path: Path = DEFAULT_OPERATIONAL_SILVER_PATH,
) -> tuple[pd.DataFrame, Path, Path]:
    """Parse all operational releases and build canonical Silver."""
    html_files = sorted(
        bronze_dir.glob(
            "*.htm"
        )
    )

    if not html_files:
        raise FileNotFoundError(
            "No operational Bronze HTML files found."
        )

    all_rows: list[dict] = []
    source_files: list[dict] = []

    for html_path in html_files:
        metadata_path = Path(
            str(html_path)
            + ".metadata.json"
        )

        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Metadata not found: {metadata_path}"
            )

        metadata = json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

        rows = parse_operational_release(
            html_path.read_bytes(),
            metadata,
        )

        for row in rows:
            row["entity_cik"] = ENTITY_CIK
            row["entity_name"] = ENTITY_NAME

            row["source"] = (
                "SEC EDGAR earnings release exhibit"
            )

            row["source_bronze_file"] = (
                html_path.name
            )

            row[
                "source_content_sha256"
            ] = metadata[
                "content_sha256"
            ]

        all_rows.extend(
            rows
        )

        source_files.append(
            {
                "file": html_path.name,
                "sha256": metadata[
                    "content_sha256"
                ],
                "accession_number": metadata[
                    "accession_number"
                ],
                "filing_date": metadata[
                    "filing_date"
                ],
            }
        )

    source_frame = pd.DataFrame(
        all_rows
    )

    canonical = canonicalize_operational_rows(
        source_frame
    )

    parquet_path, metadata_path = (
        write_operational_kpis_silver(
            canonical,
            output_path=output_path,
            source_files=source_files,
        )
    )

    return (
        canonical,
        parquet_path,
        metadata_path,
    )