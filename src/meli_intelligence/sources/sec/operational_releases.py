"""Discovery and retrieval of MercadoLibre operational earnings releases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from meli_intelligence.config.settings import SEC_USER_AGENT
from meli_intelligence.sources.sec.client import normalize_cik


SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov"


@dataclass(frozen=True)
class OperationalRelease:
    """Metadata for an SEC earnings-release exhibit."""

    cik: str
    accession_number: str
    filing_date: str
    sec_report_date: str | None
    filing_index_url: str
    exhibit_url: str
    document_name: str


def submissions_url(cik: str | int) -> str:
    normalized = normalize_cik(cik)

    return (
        f"{SEC_DATA_BASE}/submissions/"
        f"CIK{normalized}.json"
    )


def filing_index_url(
    cik: str | int,
    accession_number: str,
) -> str:
    normalized_cik = normalize_cik(cik)
    cik_numeric = str(int(normalized_cik))
    compact_accession = accession_number.replace("-", "")

    return (
        f"{SEC_ARCHIVES_BASE}/Archives/edgar/data/"
        f"{cik_numeric}/"
        f"{compact_accession}/"
        f"{accession_number}-index.html"
    )


class OperationalReleaseClient:
    """Client for discovering SEC Item 2.02 / Exhibit 99.1 releases."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_user_agent = (
            user_agent
            or SEC_USER_AGENT
        )

        if not resolved_user_agent:
            raise ValueError(
                "SEC User-Agent must be configured."
            )

        self._client = httpx.Client(
            headers={
                "User-Agent": resolved_user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def __enter__(
        self,
    ) -> "OperationalReleaseClient":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get_json(
        self,
        url: str,
    ) -> dict:
        response = self._client.get(
            url,
            headers={
                "Accept": "application/json",
            },
        )

        response.raise_for_status()

        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError(
                "SEC response must be a JSON object."
            )

        return payload

    def _get_text(
        self,
        url: str,
    ) -> str:
        response = self._client.get(
            url,
            headers={
                "Accept": "text/html,*/*",
            },
        )

        response.raise_for_status()

        return response.text

    def get_exhibit_bytes(
        self,
        release: OperationalRelease,
    ) -> bytes:
        """Retrieve the exhibit document."""
        response = self._client.get(
            release.exhibit_url,
            headers={
                "Accept": "text/html,*/*",
            },
        )

        response.raise_for_status()

        return response.content

    def _find_exhibit_991(
        self,
        index_url: str,
    ) -> tuple[str, str] | None:
        html = self._get_text(
            index_url
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for row in soup.find_all("tr"):
            cells = row.find_all("td")

            if len(cells) < 4:
                continue

            type_text = (
                cells[3]
                .get_text(
                    " ",
                    strip=True,
                )
                .upper()
                .replace(" ", "")
            )

            if type_text not in {"EX-99", "EX-99.1"}:
                continue

            document_cell = cells[2]
            link = document_cell.find(
                "a",
                href=True,
            )

            if link is None:
                continue

            href = str(link["href"])
            document_name = (
                link.get_text(
                    " ",
                    strip=True,
                )
                or href.rsplit("/", 1)[-1]
            )

            return (
                urljoin(
                    SEC_ARCHIVES_BASE,
                    href,
                ),
                document_name,
            )

        return None

    def discover_earnings_releases(
        self,
        cik: str | int,
        *,
        start_date: str | None = None,
    ) -> list[OperationalRelease]:
        """Discover recent Item 2.02 8-K filings with Exhibit 99.1."""
        normalized_cik = normalize_cik(cik)

        payload = self._get_json(
            submissions_url(
                normalized_cik
            )
        )

        recent = (
            payload
            .get("filings", {})
            .get("recent", {})
        )

        accessions = recent.get(
            "accessionNumber",
            [],
        )

        releases: list[
            OperationalRelease
        ] = []

        for index, accession in enumerate(
            accessions
        ):
            def value(
                key: str,
            ) -> str:
                values = recent.get(
                    key,
                    [],
                )

                if index >= len(values):
                    return ""

                result = values[index]

                return (
                    ""
                    if result is None
                    else str(result)
                )

            form = value("form")

            if form != "8-K":
                continue

            items = {
                item.strip()
                for item in value(
                    "items"
                ).split(",")
                if item.strip()
            }

            if "2.02" not in items:
                continue

            filing_date = value(
                "filingDate"
            )

            if (
                start_date is not None
                and filing_date < start_date
            ):
                continue

            index_url = filing_index_url(
                normalized_cik,
                str(accession),
            )

            exhibit = (
                self._find_exhibit_991(
                    index_url
                )
            )

            if exhibit is None:
                continue

            exhibit_url, document_name = (
                exhibit
            )

            sec_report_date = (
                value("reportDate")
                or None
            )

            releases.append(
                OperationalRelease(
                    cik=normalized_cik,
                    accession_number=str(
                        accession
                    ),
                    filing_date=filing_date,
                    sec_report_date=sec_report_date,
                    filing_index_url=index_url,
                    exhibit_url=exhibit_url,
                    document_name=document_name,
                )
            )

        releases.sort(
            key=lambda release: (
                release.filing_date,
                release.accession_number,
            )
        )

        return releases