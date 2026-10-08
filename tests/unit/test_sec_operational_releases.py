"""Tests for SEC operational-release discovery."""

from __future__ import annotations

import httpx

from meli_intelligence.sources.sec.operational_releases import (
    OperationalReleaseClient,
    filing_index_url,
    submissions_url,
)


def test_sec_operational_urls() -> None:
    assert submissions_url(
        "1099590"
    ) == (
        "https://data.sec.gov/submissions/"
        "CIK0001099590.json"
    )

    assert filing_index_url(
        "1099590",
        "0001099590-26-000021",
    ) == (
        "https://www.sec.gov/Archives/edgar/data/"
        "1099590/"
        "000109959026000021/"
        "0001099590-26-000021-index.html"
    )


def test_discovers_item_202_exhibit_991() -> None:
    observed_user_agents: list[
        str
    ] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        observed_user_agents.append(
            request.headers[
                "User-Agent"
            ]
        )

        if request.url.host == "data.sec.gov":
            return httpx.Response(
                200,
                json={
                    "filings": {
                        "recent": {
                            "accessionNumber": [
                                "0001099590-26-000021",
                                "0001099590-26-000020",
                            ],
                            "filingDate": [
                                "2026-08-05",
                                "2026-07-01",
                            ],
                            "reportDate": [
                                "2026-06-30",
                                "2026-07-01",
                            ],
                            "form": [
                                "8-K",
                                "8-K",
                            ],
                            "items": [
                                "2.02,9.01",
                                "5.02,9.01",
                            ],
                        }
                    }
                },
            )

        if request.url.path.endswith(
            "-index.html"
        ):
            return httpx.Response(
                200,
                text="""
                <html>
                  <table>
                    <tr>
                      <th>Seq</th>
                      <th>Description</th>
                      <th>Document</th>
                      <th>Type</th>
                    </tr>
                    <tr>
                      <td>2</td>
                      <td>Exhibit 99.1</td>
                      <td>
                        <a href="/Archives/edgar/data/1099590/example.htm">
                          example.htm
                        </a>
                      </td>
                      <td>EX-99</td>
                    </tr>
                  </table>
                </html>
                """,
            )

        raise AssertionError(
            f"Unexpected request: {request.url}"
        )

    transport = httpx.MockTransport(
        handler
    )

    with OperationalReleaseClient(
        user_agent=(
            "MELI Intelligence "
            "test@example.com"
        ),
        transport=transport,
    ) as client:
        releases = (
            client.discover_earnings_releases(
                "1099590",
                start_date="2025-01-01",
            )
        )

    assert len(releases) == 1

    release = releases[0]

    assert (
        release.accession_number
        == "0001099590-26-000021"
    )

    assert (
        release.sec_report_date
        == "2026-06-30"
    )

    assert (
        release.document_name
        == "example.htm"
    )

    assert release.exhibit_url == (
        "https://www.sec.gov/Archives/"
        "edgar/data/1099590/example.htm"
    )

    assert all(
        value
        == (
            "MELI Intelligence "
            "test@example.com"
        )
        for value in observed_user_agents
    )