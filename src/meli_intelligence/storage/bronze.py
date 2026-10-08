"""Persistence helpers for Bronze datasets."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.sources.sec.client import (
    company_facts_url,
    normalize_cik,
)


INGESTION_VERSION = "1"


def _atomic_write_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    """Write JSON atomically to reduce the risk of partial files."""
    path.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )

    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        os.replace(temporary_path, path)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def save_company_facts_bronze(
    payload: dict[str, Any],
    cik: str | int,
    *,
    bronze_dir: Path = BRONZE_DIR,
    source_url: str | None = None,
    ingestion_version: str = INGESTION_VERSION,
) -> tuple[Path, Path]:
    """Persist raw SEC Company Facts and ingestion metadata."""
    normalized_cik = normalize_cik(cik)

    destination = (
        Path(bronze_dir)
        / "sec"
        / "companyfacts"
    )

    data_path = (
        destination
        / f"CIK{normalized_cik}_companyfacts.json"
    )

    metadata_path = (
        destination
        / f"CIK{normalized_cik}_companyfacts.metadata.json"
    )

    resolved_source_url = (
        source_url
        or company_facts_url(normalized_cik)
    )

    metadata = {
        "source": "SEC EDGAR Company Facts API",
        "source_url": resolved_source_url,
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "cik": normalized_cik,
        "ingestion_version": ingestion_version,
    }

    _atomic_write_json(data_path, payload)
    _atomic_write_json(metadata_path, metadata)

    return data_path, metadata_path