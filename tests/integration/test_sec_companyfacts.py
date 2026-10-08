"""Integration tests for SEC EDGAR."""

from __future__ import annotations

import pytest

from meli_intelligence.config.settings import SEC_USER_AGENT
from meli_intelligence.sources.sec.client import SecClient


@pytest.mark.integration
def test_real_mercadolibre_company_facts() -> None:
    if not SEC_USER_AGENT:
        pytest.skip(
            "SEC_USER_AGENT is not configured."
        )

    with SecClient() as client:
        payload = client.get_company_facts("1099590")

    assert isinstance(payload, dict)
    assert str(payload["cik"]) == "1099590"
    assert payload["entityName"]
    assert isinstance(payload["facts"], dict)
