"""Offline-testable HTTP client for the Twelve Data daily MELI series."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
from typing import Any

import httpx

ENDPOINT = "https://api.twelvedata.com/time_series"
PROVIDER = "Twelve Data"
TICKER = "MELI"
INTERVAL = "1day"
DEFAULT_OUTPUTSIZE = 100
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class TwelveDataFetch:
    raw_payload: bytes
    payload: dict[str, Any]
    retrieved_at: str
    source_url: str
    requested_start_date: date | None
    requested_end_date: date | None
    outputsize: int


def _date_string(value: date | str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD).") from exc
    if isinstance(value, datetime):
        raise TypeError(f"{name} must be a date, not datetime.")
    return parsed.isoformat()


def build_request_params(
    *, start_date: date | str | None = None,
    end_date: date | str | None = None,
    outputsize: int = DEFAULT_OUTPUTSIZE,
) -> dict[str, str | int]:
    """Build nonsensitive request parameters; this never returns a secret."""
    start = _date_string(start_date, "start_date")
    end = _date_string(end_date, "end_date")
    if start and end and start > end:
        raise ValueError("start_date must be on or before end_date.")
    if isinstance(outputsize, bool) or not isinstance(outputsize, int) or not 1 <= outputsize <= 5000:
        raise ValueError("outputsize must be an integer between 1 and 5000.")
    params: dict[str, str | int] = {
        "symbol": TICKER, "interval": INTERVAL, "format": "JSON",
        "adjust": "none", "outputsize": outputsize,
    }
    if start:
        params["start_date"] = start
    if end:
        params["end_date"] = end
    return params


def sanitized_source_url(params: dict[str, str | int]) -> str:
    """Return stable, key-free provider provenance."""
    allowed = ("symbol", "interval", "format", "adjust", "start_date", "end_date", "outputsize")
    suffix = "&".join(f"{key}={params[key]}" for key in allowed if key in params)
    return f"{ENDPOINT}?{suffix}"


class TwelveDataClient:
    """Fetch daily MELI JSON. Errors intentionally omit provider body text."""

    def __init__(
        self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None, api_key: str | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive.")
        self._timeout, self._transport, self._api_key = timeout, transport, api_key

    def fetch_daily(
        self, *, start_date: date | str | None = None,
        end_date: date | str | None = None,
        outputsize: int = DEFAULT_OUTPUTSIZE,
    ) -> TwelveDataFetch:
        params = build_request_params(start_date=start_date, end_date=end_date, outputsize=outputsize)
        key = self._api_key if self._api_key is not None else os.getenv("TWELVE_DATA_API_KEY")
        if not key:
            raise ValueError("TWELVE_DATA_API_KEY is required.")
        try:
            with httpx.Client(
                timeout=self._timeout, follow_redirects=True,
                transport=self._transport, headers={"Accept": "application/json"},
            ) as client:
                response = client.get(ENDPOINT, params={**params, "apikey": key})
        except httpx.HTTPError:
            raise RuntimeError("Twelve Data request failed due to a transport error.") from None
        if response.status_code != 200:
            raise RuntimeError(f"Twelve Data request failed with HTTP {response.status_code}.")
        raw = response.content
        if not raw.strip():
            raise ValueError("Twelve Data returned an empty response.")
        if key.encode("utf-8") in raw:
            raise ValueError("Twelve Data response unexpectedly contained credential data.")
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type or raw.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError("Twelve Data returned unexpected HTML instead of JSON.")
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Twelve Data returned invalid JSON.") from None
        if not isinstance(payload, dict):
            raise ValueError("Twelve Data response must be a JSON object.")
        if str(payload.get("status", "")).lower() == "error" or ("code" in payload and "meta" not in payload):
            message = str(payload.get("message", "")).lower()
            if any(term in message for term in ("rate limit", "api credits", "quota", "api key")):
                raise RuntimeError("Twelve Data rejected the request due to quota or authentication limits.")
            raise ValueError("Twelve Data returned a provider error.")
        meta, values = payload.get("meta"), payload.get("values")
        if not isinstance(meta, dict):
            raise ValueError("Twelve Data response is missing metadata.")
        if not isinstance(values, list) or not values:
            raise ValueError("Twelve Data response is missing observations.")
        if str(meta.get("symbol", "")).upper() != TICKER:
            raise ValueError("Twelve Data returned an unexpected symbol.")
        if str(meta.get("interval", "")) != INTERVAL:
            raise ValueError("Twelve Data returned an unexpected interval.")
        if not meta.get("currency"):
            raise ValueError("Twelve Data metadata is missing currency.")
        if not meta.get("exchange"):
            raise ValueError("Twelve Data metadata is missing exchange.")
        return TwelveDataFetch(
            raw_payload=raw, payload=payload, retrieved_at=datetime.now(timezone.utc).isoformat(),
            source_url=sanitized_source_url(params),
            requested_start_date=date.fromisoformat(params["start_date"]) if "start_date" in params else None,
            requested_end_date=date.fromisoformat(params["end_date"]) if "end_date" in params else None,
            outputsize=outputsize,
        )
