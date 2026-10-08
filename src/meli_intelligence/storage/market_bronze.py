"""Immutable raw JSON Bronze storage for Twelve Data price responses."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.sources.market.twelve_data import TwelveDataFetch

DEFAULT_MARKET_BRONZE_DIR = BRONZE_DIR / "market" / "twelve_data"


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite Market Bronze file: {path.name}")
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def save_market_bronze(
    fetch: TwelveDataFetch, *, bronze_dir: Path = DEFAULT_MARKET_BRONZE_DIR,
) -> tuple[Path, Path, str]:
    if "apikey" in fetch.source_url.lower() or b"apikey" in fetch.raw_payload.lower():
        raise ValueError("Market Bronze payload or provenance contains a forbidden credential marker.")
    digest = hashlib.sha256(fetch.raw_payload).hexdigest()
    retrieved_key = datetime.fromisoformat(fetch.retrieved_at).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"MELI_1day_{retrieved_key}_{digest[:12]}.json"
    directory = Path(bronze_dir)
    raw_path, metadata_path = directory / filename, directory / f"{filename}.metadata.json"
    if raw_path.exists() or metadata_path.exists():
        if raw_path.exists() and metadata_path.exists() and raw_path.read_bytes() == fetch.raw_payload:
            prior_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if prior_metadata.get("payload_sha256") == digest and prior_metadata.get("source_url") == fetch.source_url:
                return raw_path, metadata_path, digest
        raise FileExistsError(f"Refusing to overwrite Market Bronze payload: {raw_path.name}")
    metadata: dict[str, Any] = {
        "provider": "Twelve Data", "source": "Twelve Data", "requested_ticker": "MELI",
        "interval": "1day", "adjust": "none",
        "requested_start_date": fetch.requested_start_date.isoformat() if fetch.requested_start_date else None,
        "requested_end_date": fetch.requested_end_date.isoformat() if fetch.requested_end_date else None,
        "outputsize": fetch.outputsize, "retrieved_at": fetch.retrieved_at,
        "source_url": fetch.source_url, "payload_sha256": digest, "payload_file": filename,
    }
    _atomic_write(raw_path, fetch.raw_payload)
    try:
        _atomic_write(metadata_path, (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception:
        raw_path.unlink(missing_ok=True)
        raise
    return raw_path, metadata_path, digest
