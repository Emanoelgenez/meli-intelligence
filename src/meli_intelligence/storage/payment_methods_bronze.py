"""Immutable raw-page Bronze storage for BCB payment-method data."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.sources.bcb.payment_methods_client import PaymentMethodsFetch


INGESTION_VERSION = "1"
DEFAULT_PAYMENT_METHODS_BRONZE_DIR = BRONZE_DIR / "bcb" / "payment_methods"


def _atomic_create(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite payment-method Bronze: {path}")
        os.rename(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def save_payment_methods_bronze(
    fetch: PaymentMethodsFetch,
    *,
    bronze_dir: Path = DEFAULT_PAYMENT_METHODS_BRONZE_DIR,
    ingestion_version: str = INGESTION_VERSION,
) -> list[tuple[Path, Path]]:
    """Persist every untouched response page and its independent metadata."""
    paths = []
    for page_index, page in enumerate(fetch.pages):
        digest = hashlib.sha256(page.raw_payload).hexdigest()
        safe_stamp = page.retrieved_at.replace(":", "").replace("-", "")
        filename = (
            f"mpv_{fetch.requested_start_month}_p{page_index:04d}_"
            f"{safe_stamp}_{digest[:12]}.json"
        )
        directory = Path(bronze_dir)
        raw_path = directory / filename
        metadata_path = directory / f"{filename}.metadata.json"
        metadata: dict[str, Any] = {
            "source": "Banco Central do Brasil",
            "provider": "BCB",
            "dataset": "Meios de Pagamentos Mensais",
            "endpoint": "MPV_DadosAbertos/MeiosdePagamentosMensalDA",
            "requested_start_month": fetch.requested_start_month,
            "source_url": page.source_url,
            "retrieved_at": page.retrieved_at,
            "ingestion_version": ingestion_version,
            "payload_sha256": digest,
            "payload_file": raw_path.name,
            "page_index": page_index,
        }
        if raw_path.exists() or metadata_path.exists():
            raise FileExistsError(f"Refusing to overwrite payment-method Bronze: {raw_path}")
        _atomic_create(raw_path, page.raw_payload)
        try:
            _atomic_create(
                metadata_path,
                (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        except Exception:
            raw_path.unlink(missing_ok=True)
            raise
        paths.append((raw_path, metadata_path))
    return paths
