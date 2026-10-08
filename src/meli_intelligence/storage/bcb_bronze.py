"""Immutable raw-payload Bronze storage for BCB SGS requests."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.metadata.bcb_series import get_bcb_series
from meli_intelligence.sources.bcb.sgs_client import BCBFetch


INGESTION_VERSION = "1"
DEFAULT_BCB_SGS_BRONZE_DIR = BRONZE_DIR / "bcb" / "sgs"


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


def save_bcb_sgs_bronze(
    fetch: BCBFetch,
    *,
    bronze_dir: Path = DEFAULT_BCB_SGS_BRONZE_DIR,
    ingestion_version: str = INGESTION_VERSION,
) -> tuple[Path, Path]:
    """Persist one original BCB payload and request-level provenance."""
    series = get_bcb_series(fetch.series_code)
    digest = hashlib.sha256(fetch.raw_payload).hexdigest()
    retrieved_key = datetime.fromisoformat(fetch.retrieved_at).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    filename = (
        f"{fetch.series_code}_{fetch.requested_start_date.isoformat()}_"
        f"{fetch.requested_end_date.isoformat()}_{retrieved_key}_{digest[:12]}.json"
    )
    destination = Path(bronze_dir)
    data_path = destination / filename
    metadata_path = destination / f"{filename}.metadata.json"
    if data_path.exists() or metadata_path.exists():
        raise FileExistsError(f"Refusing to overwrite BCB Bronze payload: {data_path}")
    metadata = {
        "source": "Banco Central do Brasil",
        "provider": "BCB",
        "dataset": "SGS",
        "series_code": fetch.series_code,
        "metric_id": series.metric_id,
        "source_url": fetch.source_url,
        "requested_start_date": fetch.requested_start_date.isoformat(),
        "requested_end_date": fetch.requested_end_date.isoformat(),
        "retrieved_at": fetch.retrieved_at,
        "ingestion_version": ingestion_version,
        "payload_sha256": digest,
        "payload_file": data_path.name,
    }
    _atomic_write(data_path, fetch.raw_payload)
    _atomic_write_json(metadata_path, metadata)
    return data_path, metadata_path
