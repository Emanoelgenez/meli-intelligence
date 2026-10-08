"""Client for the official SEC EDGAR APIs."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from meli_intelligence.config.settings import SEC_USER_AGENT


LOGGER = logging.getLogger(__name__)

SEC_BASE_URL = "https://data.sec.gov"
DEFAULT_TIMEOUT_SECONDS = 30.0


def normalize_cik(cik: str | int) -> str:
    """Return an SEC CIK normalized to ten digits."""
    value = str(cik).strip()

    if value.upper().startswith("CIK"):
        value = value[3:]

    if not value.isdigit():
        raise ValueError("CIK must contain only digits.")

    if len(value) > 10:
        raise ValueError("CIK cannot contain more than 10 digits.")

    return value.zfill(10)


def company_facts_url(cik: str | int) -> str:
    """Build the official SEC Company Facts URL."""
    normalized_cik = normalize_cik(cik)

    return (
        f"{SEC_BASE_URL}/api/xbrl/companyfacts/"
        f"CIK{normalized_cik}.json"
    )


class SecClient:
    """Minimal client for SEC EDGAR structured-data APIs."""

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_user_agent = (user_agent or SEC_USER_AGENT or "").strip()

        if not resolved_user_agent:
            raise ValueError(
                "SEC_USER_AGENT is required for SEC requests. "
                "Configure it in the environment or local .env file."
            )

        self._client = httpx.Client(
            base_url=SEC_BASE_URL,
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": resolved_user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "SecClient":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()

    def get_company_facts(self, cik: str | int) -> dict[str, Any]:
        """Download Company Facts for a company from the SEC."""
        normalized_cik = normalize_cik(cik)

        path = (
            "/api/xbrl/companyfacts/"
            f"CIK{normalized_cik}.json"
        )

        LOGGER.info(
            "Starting SEC Company Facts download for CIK %s",
            normalized_cik,
        )

        try:
            response = self._client.get(path)
            response.raise_for_status()
        except httpx.HTTPStatusError:
            LOGGER.exception(
                "SEC Company Facts request failed for CIK %s",
                normalized_cik,
            )
            raise

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(
                "SEC Company Facts response must be a JSON object."
            )

        response_cik = payload.get("cik")

        if response_cik is None:
            raise ValueError(
                "SEC Company Facts response does not contain a CIK."
            )

        if normalize_cik(response_cik) != normalized_cik:
            raise ValueError(
                "SEC Company Facts response CIK does not match "
                "the requested entity."
            )

        entity_name = payload.get("entityName")

        if not isinstance(entity_name, str) or not entity_name.strip():
            raise ValueError(
                "SEC Company Facts response does not contain "
                "a valid entityName."
            )

        facts = payload.get("facts")

        if not isinstance(facts, dict):
            raise ValueError(
                "SEC Company Facts response does not contain "
                "a valid facts structure."
            )

        LOGGER.info(
            "SEC Company Facts download completed for CIK %s",
            normalized_cik,
        )

        return payload

