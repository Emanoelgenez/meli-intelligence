"""Offline Twelve Data client and market transformation contracts."""
from __future__ import annotations

from datetime import date
import hashlib
import json

import httpx
import pandas as pd
import pytest

from meli_intelligence.sources.market.twelve_data import (
    TwelveDataClient, build_request_params,
)
from meli_intelligence.transformations.market_prices import normalize_market_prices


def payload(*, values=None, **meta_updates):
    meta = {"symbol": "MELI", "interval": "1day", "currency": "USD", "exchange": "NASDAQ", "mic_code": "XNGS"}
    meta.update(meta_updates)
    return {"meta": meta, "values": values or [
        {"datetime": "2026-10-02", "open": "2000", "high": "2020", "low": "1990", "close": "2010", "volume": "1234"},
        {"datetime": "2026-10-05", "open": "2011", "high": "2030", "low": "2000", "close": "2025", "volume": "1400"},
    ]}


def _client(body, *, status=200, content_type="application/json", api_key=None):
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=content, headers={"content-type": content_type}))
    return TwelveDataClient(transport=transport, api_key=api_key or ("offline" + "-test-" + "key"))


def test_request_contract_dates_and_no_secret_in_pure_params():
    params = build_request_params(start_date="2026-01-01", end_date=date(2026, 2, 1), outputsize=30)
    assert params == {"symbol": "MELI", "interval": "1day", "format": "JSON", "adjust": "none", "outputsize": 30,
                      "start_date": "2026-01-01", "end_date": "2026-02-01"}
    with pytest.raises(ValueError, match="on or before"):
        build_request_params(start_date="2026-02-02", end_date="2026-02-01")
    with pytest.raises(ValueError, match="outputsize"):
        build_request_params(outputsize=0)


def test_api_key_required_without_echoing_value(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TWELVE_DATA_API_KEY is required"):
        TwelveDataClient().fetch_daily()


def test_successful_fetch_metadata_provenance_and_api_key_not_persisted():
    key = "offline" + "-test-" + "key"
    captured = {}
    response_body = json.dumps(payload()).encode()
    transport = httpx.MockTransport(lambda request: captured.update(query=dict(request.url.params)) or httpx.Response(200, content=response_body, headers={"content-type": "application/json"}))
    client = TwelveDataClient(transport=transport, api_key=key)
    fetched = client.fetch_daily(start_date="2026-10-01", outputsize=20)
    assert fetched.payload["meta"]["currency"] == "USD"
    assert fetched.source_url.startswith("https://api.twelvedata.com/time_series?")
    assert "apikey" not in fetched.source_url.lower() and key not in fetched.source_url
    assert fetched.source_url.endswith("start_date=2026-10-01&outputsize=20")
    assert captured["query"]["apikey"] == key
    assert "apikey" not in fetched.source_url.lower()
    assert fetched.raw_payload


@pytest.mark.parametrize("body, status, content_type, match", [
    (b"", 200, "application/json", "empty"),
    (b"<html>challenge</html>", 200, "text/html", "HTML"),
    (b"not-json", 200, "application/json", "invalid JSON"),
    ({"status": "error", "message": "bad request"}, 200, "application/json", "provider error"),
    ({"status": "error", "message": "This key hit the API credits limit"}, 200, "application/json", "quota"),
    ({"values": []}, 200, "application/json", "metadata"),
    ({"meta": {"symbol": "MELI", "interval": "1day", "currency": "USD", "exchange": "NASDAQ"}, "values": []}, 200, "application/json", "observations"),
    (payload(**{"symbol": "OTHER"}), 200, "application/json", "symbol"),
    (payload(**{"interval": "1h"}), 200, "application/json", "interval"),
    (payload(**{"currency": None}), 200, "application/json", "currency"),
    (payload(**{"exchange": None}), 200, "application/json", "exchange"),
])
def test_provider_response_contract_errors(body, status, content_type, match):
    with pytest.raises((ValueError, RuntimeError), match=match):
        _client(body, status=status, content_type=content_type).fetch_daily()


def test_http_failure_and_provider_echoed_secret_are_redacted():
    with pytest.raises(RuntimeError, match="HTTP 503"):
        _client(payload(), status=503).fetch_daily()
    key = "unit" + "-only-" + "secret"
    client = _client({"meta": payload()["meta"], "values": [{**payload()["values"][0], "note": key}]}, api_key=key)
    with pytest.raises(ValueError) as error:
        client.fetch_daily()
    assert key not in str(error.value)

    client = _client({"status": "error", "message": f"{key} quota exceeded"}, api_key=key)
    with pytest.raises((RuntimeError, ValueError)) as error:
        client.fetch_daily()
    assert key not in str(error.value)


def test_transport_failure_is_redacted():
    def fail(_request):
        raise httpx.ConnectError("offline transport failure")
    client = TwelveDataClient(transport=httpx.MockTransport(fail), api_key="offline-key")
    with pytest.raises(RuntimeError, match="transport error") as error:
        client.fetch_daily()
    assert "offline-key" not in str(error.value)


def test_transform_preserves_dates_gaps_metadata_and_nullable_volume():
    raw = payload(values=[
        {"datetime": "2026-10-05", "open": "11", "high": "12", "low": "10", "close": "11.5"},
        {"datetime": "2026-10-02", "open": "10", "high": "11", "low": "9", "close": "10.5", "volume": "3"},
    ])
    fetched = _client(raw).fetch_daily()
    digest = hashlib.sha256(fetched.raw_payload).hexdigest()
    frame = normalize_market_prices(fetched, source_bronze_file="raw.json", source_content_sha256=digest)
    assert list(frame.reference_date) == [date(2026, 10, 2), date(2026, 10, 5)]
    assert frame.ticker.tolist() == ["MELI", "MELI"]
    assert frame.entity.eq("MercadoLibre, Inc.").all()
    assert frame.currency.eq("USD").all() and frame.exchange.eq("NASDAQ").all()
    assert frame.mic_code.eq("XNGS").all()
    assert frame.volume.iloc[0] == 3 and pd.isna(frame.volume.iloc[1])
    assert frame.source_bronze_file.eq("raw.json").all()
    assert frame.source_content_sha256.eq(digest).all()


@pytest.mark.parametrize("override, match", [
    ({"close": "NaN"}, "finite"), ({"high": "8"}, "inconsistent"),
    ({"open": "99"}, "inconsistent"), ({"close": "99"}, "inconsistent"),
    ({"volume": "-1"}, "nonnegative"), ({"volume": "Infinity"}, "finite"),
    ({"open": None}, "numeric"),
])
def test_transform_rejects_invalid_numeric_and_ohlc(override, match):
    row = {"datetime": "2026-10-05", "open": "10", "high": "12", "low": "9", "close": "11", "volume": "2"}
    row.update(override)
    fetched = _client(payload(values=[row])).fetch_daily()
    with pytest.raises(ValueError, match=match):
        normalize_market_prices(fetched, source_bronze_file="raw.json", source_content_sha256="a" * 64)


def test_transform_deduplicates_identical_but_rejects_conflicting_key():
    row = payload()["values"][0]
    fetched = _client(payload(values=[row, dict(row)])).fetch_daily()
    result = normalize_market_prices(fetched, source_bronze_file="raw.json", source_content_sha256="b" * 64)
    assert len(result) == 1
    conflicting = dict(row, close="2011")
    fetched = _client(payload(values=[row, conflicting])).fetch_daily()
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        normalize_market_prices(fetched, source_bronze_file="raw.json", source_content_sha256="b" * 64)
