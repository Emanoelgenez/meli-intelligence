"""Small, auditable HTTP client for official IBGE SIDRA JSON responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

import httpx

from meli_intelligence.metadata.ibge_series import (
    SIDRAClassificationFilter,
    get_ibge_series,
)


SIDRA_TIMEOUT_SECONDS = 30.0
SIDRA_USER_AGENT = "MELI Intelligence/1.0 (official macro data ingestion)"


@dataclass(frozen=True)
class SIDRAFetch:
    table_id: int
    variable_id: int
    source_url: str
    retrieved_at: str
    raw_payload: bytes
    records: list[dict[str, Any]]


class SIDRAClient:
    def __init__(self, *, timeout: float = SIDRA_TIMEOUT_SECONDS,
                 client: httpx.Client | None = None) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive.")
        self.timeout = timeout
        self._client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": SIDRA_USER_AGENT}
        )
        self._owns_client = client is None

    def fetch_variable(
        self,
        table_id: int,
        variable_id: int,
        *,
        classification_filters: tuple[SIDRAClassificationFilter, ...] | None = None,
    ) -> SIDRAFetch:
        series = get_ibge_series(table_id, variable_id)
        url = series.source_url(classification_filters=classification_filters)
        response = self._client.get(url, timeout=self.timeout)
        response.raise_for_status()
        raw = response.content
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError("IBGE SIDRA returned invalid JSON.") from exc
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ValueError("IBGE SIDRA payload must be an array of JSON objects.")
        if payload and len(payload) < 2:
            raise ValueError("IBGE SIDRA payload is missing data rows.")
        return SIDRAFetch(
            table_id, variable_id, str(response.request.url),
            datetime.now(timezone.utc).isoformat(), raw, payload
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SIDRAClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
