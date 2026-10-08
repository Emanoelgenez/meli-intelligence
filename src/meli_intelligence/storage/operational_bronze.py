"""Bronze storage for raw SEC operational earnings releases."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.sources.sec.operational_releases import (
    OperationalRelease,
)


INGESTION_VERSION = "1"


def _sha256(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def _safe_document_name(
    value: str,
) -> str:
    return "".join(
        character
        if (
            character.isalnum()
            or character in {
                ".",
                "-",
                "_",
            }
        )
        else "_"
        for character in value
    )


def _atomic_write_bytes(
    path: Path,
    content: bytes,
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
            "wb",
        ) as file:
            file.write(
                content
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


def save_operational_release_bronze(
    content: bytes,
    release: OperationalRelease,
    *,
    ingestion_version: str = INGESTION_VERSION,
) -> tuple[Path, Path]:
    """Persist one raw Exhibit 99.1 plus provenance metadata."""
    safe_document = _safe_document_name(
        release.document_name
    )

    compact_accession = (
        release.accession_number
        .replace("-", "")
    )

    directory = (
        BRONZE_DIR
        / "sec"
        / "operational_releases"
    )

    filename = (
        f"{release.filing_date}_"
        f"{compact_accession}_"
        f"{safe_document}"
    )

    html_path = (
        directory
        / filename
    )

    metadata_path = (
        directory
        / f"{filename}.metadata.json"
    )

    retrieved_at = datetime.now(
        timezone.utc
    ).isoformat()

    metadata = {
        "source": (
            "SEC EDGAR earnings release exhibit"
        ),
        "source_url": (
            release.exhibit_url
        ),
        "retrieved_at": (
            retrieved_at
        ),
        # SEC reportDate on an 8-K represents the current
        # report/event date, not necessarily the economic
        # quarter covered by the earnings release.
        #
        # The true operational reference period is extracted
        # from the release content during transformation.
        "reference_period": None,
        "ingestion_version": (
            ingestion_version
        ),
        "cik": release.cik,
        "accession_number": (
            release.accession_number
        ),
        "filing_date": (
            release.filing_date
        ),
        "sec_report_date": (
            release.sec_report_date
        ),
        "filing_index_url": (
            release.filing_index_url
        ),
        "document_name": (
            release.document_name
        ),
        "content_sha256": (
            _sha256(content)
        ),
    }

    _atomic_write_bytes(
        html_path,
        content,
    )

    _atomic_write_json(
        metadata_path,
        metadata,
    )

    return (
        html_path,
        metadata_path,
    )