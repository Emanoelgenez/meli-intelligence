"""HTTP client for the official BCB SGS time-series API."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from meli_intelligence.metadata.bcb_series import get_bcb_series


LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_WINDOW_YEARS = 10
DEFAULT_USER_AGENT = "MELI Intelligence"


@dataclass(frozen=True)
class BCBFetch:
    """One auditable HTTP response for a single inclusive date window."""

    series_code: int
    requested_start_date: date
    requested_end_date: date
    source_url: str
    retrieved_at: str
    raw_payload: bytes
    records: list[dict[str, Any]]


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        # Feb 29 becomes Feb 28 when the target year is not a leap year.
        return value.replace(year=value.year + years, day=28)


def _max_window_end(start_date: date) -> date:
    """Return a conservative inclusive endpoint under the 10-year limit."""
    return _add_years(start_date, MAX_WINDOW_YEARS) - timedelta(days=1)


def _validate_dates(start_date: date, end_date: date) -> None:
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise TypeError("start_date and end_date must be datetime.date values.")
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")


def _chunks(start_date: date, end_date: date) -> list[tuple[date, date]]:
    _validate_dates(start_date, end_date)
    result = []
    current = start_date
    while current <= end_date:
        window_end = min(_max_window_end(current), end_date)
        result.append((current, window_end))
        current = window_end + timedelta(days=1)
    return result


class BCBSeriesClient:
    """Fetch raw JSON from BCB SGS with deterministic <=10-year windows."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive.")
        if not user_agent.strip():
            raise ValueError("user_agent cannot be empty.")
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": user_agent.strip(),
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> BCBSeriesClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def fetch_series_window(
        self,
        series_code: int,
        start_date: date,
        end_date: date,
    ) -> BCBFetch:
        """Fetch one inclusive window of at most ten calendar years."""
        _validate_dates(start_date, end_date)
        if end_date > _max_window_end(start_date):
            raise ValueError("A single BCB SGS request cannot exceed 10 years.")
        series = get_bcb_series(series_code)
        url = series.source_url()
        params = {
            "formato": "json",
            "dataInicial": start_date.strftime("%d/%m/%Y"),
            "dataFinal": end_date.strftime("%d/%m/%Y"),
        }
        LOGGER.info(
            "Fetching BCB SGS series %s (%s) from %s to %s",
            series_code,
            series.metric_id,
            params["dataInicial"],
            params["dataFinal"],
        )
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            LOGGER.exception("BCB SGS request failed for series %s", series_code)
            raise
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            content_type = response.headers.get("content-type", "")
            body_snippet = " ".join(
                response.content.decode("utf-8", errors="replace").split()
            )[:200]
            raise ValueError(
                "BCB SGS response is not valid JSON "
                f"(status={response.status_code}, content_type={content_type!r}, "
                f"body={body_snippet!r})."
            ) from exc
        if not isinstance(payload, list):
            raise ValueError("BCB SGS response must be a JSON array.")
        for index, record in enumerate(payload):
            if not isinstance(record, dict) or not {"data", "valor"}.issubset(record):
                raise ValueError(
                    f"BCB SGS record {index} must contain data and valor fields."
                )
            if not isinstance(record["data"], str) or not isinstance(
                record["valor"], (str, int, float)
            ) or isinstance(record["valor"], bool):
                raise ValueError(f"BCB SGS record {index} has invalid field types.")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        return BCBFetch(
            series_code=series_code,
            requested_start_date=start_date,
            requested_end_date=end_date,
            source_url=str(response.request.url),
            retrieved_at=retrieved_at,
            raw_payload=response.content,
            records=payload,
        )

    def fetch_series(
        self,
        series_code: int,
        start_date: date,
        end_date: date,
    ) -> list[BCBFetch]:
        """Fetch a date range in conservative inclusive ten-year chunks."""
        return [
            self.fetch_series_window(series_code, chunk_start, chunk_end)
            for chunk_start, chunk_end in _chunks(start_date, end_date)
        ]
