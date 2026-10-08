"""HTTP client for BCB Olinda monthly payment-method statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx


PAYMENT_METHODS_ENDPOINT = (
    "https://olinda.bcb.gov.br/olinda/servico/MPV_DadosAbertos/"
    "versao/v1/odata/MeiosdePagamentosMensalDA(AnoMes=@AnoMes)"
)
PAYMENT_METHODS_TIMEOUT_SECONDS = 30.0
PAYMENT_METHODS_USER_AGENT = "MELI Intelligence/1.0 (official macro data ingestion)"


@dataclass(frozen=True)
class PaymentMethodsPage:
    source_url: str
    retrieved_at: str
    raw_payload: bytes
    records: list[dict[str, Any]]


@dataclass(frozen=True)
class PaymentMethodsFetch:
    requested_start_month: str
    pages: tuple[PaymentMethodsPage, ...]

    @property
    def records(self) -> list[dict[str, Any]]:
        return [record for page in self.pages for record in page.records]

    @property
    def source_url(self) -> str:
        return self.pages[0].source_url

    @property
    def retrieved_at(self) -> str:
        return self.pages[0].retrieved_at


def _validate_month(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{6}", value):
        raise ValueError("month must have YYYYMM format.")
    year, month = int(value[:4]), int(value[4:])
    if year < 1 or not 1 <= month <= 12:
        raise ValueError(f"Invalid YYYYMM month: {value!r}.")


class PaymentMethodsClient:
    """Fetch the complete OData result, preserving every raw page."""

    def __init__(
        self,
        *,
        timeout: float = PAYMENT_METHODS_TIMEOUT_SECONDS,
        user_agent: str = PAYMENT_METHODS_USER_AGENT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive.")
        if not user_agent.strip():
            raise ValueError("user_agent cannot be empty.")
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": user_agent.strip(), "Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PaymentMethodsClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch_monthly_payment_methods(self, start_month: str) -> PaymentMethodsFetch:
        """Fetch records from the requested lower-bound month through latest."""
        _validate_month(start_month)
        params: dict[str, str] | None = {
            "@AnoMes": f"'{start_month}'",
            "$format": "json",
            "$select": "AnoMes,quantidadePix,valorPix",
        }
        url = PAYMENT_METHODS_ENDPOINT
        pages: list[PaymentMethodsPage] = []
        while url:
            response = self._client.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            try:
                payload = response.json()
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                snippet = " ".join(response.content.decode("utf-8", "replace").split())[:200]
                raise ValueError(
                    "BCB payment-method response is not valid JSON "
                    f"(status={response.status_code}, "
                    f"content_type={response.headers.get('content-type', '')!r}, "
                    f"body={snippet!r})."
                ) from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                raise ValueError("BCB payment-method payload must be an object with a value list.")
            records = payload["value"]
            for index, record in enumerate(records):
                if not isinstance(record, dict) or not {
                    "AnoMes", "quantidadePix", "valorPix"
                }.issubset(record):
                    raise ValueError(
                        f"BCB payment-method record {index} is missing required fields."
                    )
                month = record["AnoMes"]
                _validate_month(month)
                if month < start_month:
                    raise ValueError(
                        f"BCB payment-method record month {month} precedes "
                        f"requested lower bound {start_month}."
                    )
            pages.append(
                PaymentMethodsPage(
                    source_url=str(response.request.url),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    raw_payload=response.content,
                    records=records,
                )
            )
            next_link = payload.get("@odata.nextLink") or payload.get("odata.nextLink")
            if next_link is not None and not isinstance(next_link, str):
                raise ValueError("BCB payment-method nextLink must be a string.")
            url = urljoin(str(response.request.url), next_link) if next_link else ""
            params = None
        return PaymentMethodsFetch(start_month, tuple(pages))
