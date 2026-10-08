"""Unit tests for the SEC client."""

from __future__ import annotations

import httpx
import pytest

from meli_intelligence.sources.sec.client import (
    SecClient,
    company_facts_url,
    normalize_cik,
)


def test_normalize_cik() -> None:
    assert normalize_cik("1099590") == "0001099590"
    assert normalize_cik(1099590) == "0001099590"
    assert normalize_cik("CIK0001099590") == "0001099590"


def test_company_facts_url() -> None:
    assert company_facts_url("1099590") == (
        "https://data.sec.gov/api/xbrl/companyfacts/"
        "CIK0001099590.json"
    )


def test_company_facts_request_uses_expected_url_and_user_agent() -> None:
    observed: dict[str, str] = {}

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["user_agent"] = request.headers["User-Agent"]

        return httpx.Response(
            200,
            json={
                "cik": 1099590,
                "entityName": "MercadoLibre, Inc.",
                "facts": {},
            },
        )

    transport = httpx.MockTransport(handler)

    with SecClient(
        user_agent="MELI Intelligence test@example.com",
        transport=transport,
    ) as client:
        payload = client.get_company_facts("1099590")

    assert payload["cik"] == 1099590
    assert observed["url"] == (
        "https://data.sec.gov/api/xbrl/companyfacts/"
        "CIK0001099590.json"
    )
    assert (
        observed["user_agent"]
        == "MELI Intelligence test@example.com"
    )


def test_company_facts_http_error_is_not_hidden() -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            429,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    with SecClient(
        user_agent="MELI Intelligence test@example.com",
        transport=transport,
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.get_company_facts("1099590")
