"""Immutable raw-response Bronze storage for IBGE SIDRA variables."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.metadata.ibge_series import get_ibge_series
from meli_intelligence.sources.ibge.sidra_client import SIDRAFetch


INGESTION_VERSION = "1"
DEFAULT_IBGE_SIDRA_BRONZE_DIR = BRONZE_DIR / "ibge" / "sidra"


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite IBGE Bronze file: {path}")
        os.rename(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write(path, encoded)


def save_ibge_sidra_bronze(
    fetch: SIDRAFetch, *, bronze_dir: Path = DEFAULT_IBGE_SIDRA_BRONZE_DIR,
    ingestion_version: str = INGESTION_VERSION,
) -> tuple[Path, Path]:
    series = get_ibge_series(fetch.table_id, fetch.variable_id)
    digest = hashlib.sha256(fetch.raw_payload).hexdigest()
    timestamp = datetime.fromisoformat(fetch.retrieved_at).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"t{fetch.table_id}_v{fetch.variable_id}_{timestamp}_{digest[:12]}.json"
    directory = Path(bronze_dir)
    payload_path = directory / filename
    metadata_path = directory / f"{filename}.metadata.json"
    if payload_path.exists() or metadata_path.exists():
        raise FileExistsError(f"Refusing to overwrite IBGE Bronze payload: {payload_path}")
    metadata = {
        "source": "IBGE", "provider": "IBGE", "dataset": "SIDRA",
        "table_id": fetch.table_id, "variable_id": fetch.variable_id,
        "metric_id": series.metric_id, "territorial_level": series.territorial_level,
        "territory": series.territory, "source_url": fetch.source_url,
        "retrieved_at": fetch.retrieved_at, "ingestion_version": ingestion_version,
        "payload_sha256": digest, "payload_file": payload_path.name,
    }
    _atomic_write(payload_path, fetch.raw_payload)
    try:
        _atomic_json(metadata_path, metadata)
    except Exception:
        payload_path.unlink(missing_ok=True)
        raise
    return payload_path, metadata_path
