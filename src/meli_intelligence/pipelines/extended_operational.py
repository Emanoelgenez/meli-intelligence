"""Pipeline for extended operational KPIs and evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.storage.extended_operational import (
    write_extended_silver,
)
from meli_intelligence.transformations.extended_operational import (
    parse_extended_release,
)


ENTITY_CIK = "0001099590"
ENTITY_NAME = "MercadoLibre, Inc."

DEFAULT_BRONZE_DIR = (
    BRONZE_DIR
    / "sec"
    / "operational_releases"
)


def build_extended_operational_silver(
    *,
    bronze_dir: Path = DEFAULT_BRONZE_DIR,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    tuple[Path, Path, Path, Path],
]:
    """Build structured extended KPIs and evidence facts."""
    fact_rows = []
    evidence_rows = []
    source_files = []

    html_files = sorted(
        bronze_dir.glob(
            "*.htm"
        )
    )

    if not html_files:
        raise FileNotFoundError(
            "No operational Bronze releases found."
        )

    for html_path in html_files:
        metadata_path = Path(
            str(html_path)
            + ".metadata.json"
        )

        metadata = json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

        facts, evidence = (
            parse_extended_release(
                html_path.read_bytes(),
                metadata,
            )
        )

        common = {
            "entity_cik": ENTITY_CIK,
            "entity_name": ENTITY_NAME,
            "source_bronze_file": (
                html_path.name
            ),
            "source_content_sha256": (
                metadata[
                    "content_sha256"
                ]
            ),
        }

        for row in facts:
            row.update(
                common
            )

        for row in evidence:
            row.update(
                common
            )

        fact_rows.extend(
            facts
        )

        evidence_rows.extend(
            evidence
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

    facts = pd.DataFrame(
        fact_rows
    )

    evidence = pd.DataFrame(
        evidence_rows
    )

    paths = write_extended_silver(
        facts,
        evidence,
        source_files=source_files,
    )

    return (
        facts,
        evidence,
        paths,
    )