"""Offline tests for the official BCB SGS client."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from meli_intelligence.metadata.bcb_series import get_bcb_series
from meli_intelligence.sources.bcb.sgs_client import BCBSeriesClient


def test_sgs_url_params_user_agent_and_timeout() -> None:
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["timeout"] = request.extensions.get("timeout")
        observed["user_agent"] = request.headers["User-Agent"]
        return httpx.Response(200, json=[])

    with BCBSeriesClient(
        timeout=17,
        user_agent="MELI Intelligence tests",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.fetch_series_window(
            432, date(2023, 1, 1), date(2023, 12, 31)
        )

    assert observed["url"] == (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
        "?formato=json&dataInicial=01%2F01%2F2023&dataFinal=31%2F12%2F2023"
    )
    assert observed["timeout"] is not None
    assert observed["user_agent"] == "MELI Intelligence tests"


def test_sgs_http_and_json_errors_are_explicit() -> None:
    def http_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with BCBSeriesClient(transport=httpx.MockTransport(http_error)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.fetch_series_window(432, date(2023, 1, 1), date(2023, 1, 2))

    def invalid_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"},
            content=b"<html>" + (b"x" * 250) + b"</html>",
        )

    with BCBSeriesClient(transport=httpx.MockTransport(invalid_json)) as client:
        with pytest.raises(ValueError, match="status=200.*content_type='text/html'.*body=") as error:
            client.fetch_series_window(432, date(2023, 1, 1), date(2023, 1, 2))
    assert len(str(error.value).split("body=", 1)[1].split(").", 1)[0]) <= 202


def test_sgs_invalid_date_ranges_fail_before_request() -> None:
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not be made")

    with BCBSeriesClient(transport=httpx.MockTransport(fail_if_called)) as client:
        with pytest.raises(ValueError, match="start_date"):
            client.fetch_series(432, date(2023, 1, 2), date(2023, 1, 1))
        with pytest.raises(ValueError, match="cannot exceed 10 years"):
            client.fetch_series_window(
                432, date(2000, 1, 1), date(2010, 1, 1)
            )


def test_long_sgs_range_chunks_without_gaps_or_overlaps() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    start, end = date(2000, 1, 1), date(2021, 1, 1)
    with BCBSeriesClient(transport=httpx.MockTransport(handler)) as client:
        chunks = client.fetch_series(432, start, end)

    assert len(chunks) == len(requests) == 3
    assert (
        chunks[0].requested_start_date,
        chunks[0].requested_end_date,
    ) == (date(2000, 1, 1), date(2009, 12, 31))
    assert (
        chunks[1].requested_start_date,
        chunks[1].requested_end_date,
    ) == (date(2010, 1, 1), date(2019, 12, 31))
    assert (
        chunks[-1].requested_start_date,
        chunks[-1].requested_end_date,
    ) == (date(2020, 1, 1), date(2021, 1, 1))
    for current, following in zip(chunks, chunks[1:], strict=False):
        assert following.requested_start_date == current.requested_end_date + timedelta(days=1)
    assert chunks[0].requested_start_date == start
    assert chunks[-1].requested_end_date == end
    for chunk in chunks:
        assert (chunk.requested_end_date - chunk.requested_start_date).days < 3653


def test_leap_day_range_chunks_contiguously() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    with BCBSeriesClient(transport=httpx.MockTransport(handler)) as client:
        chunks = client.fetch_series(432, date(2016, 2, 29), date(2026, 3, 2))

    assert [
        (chunk.requested_start_date, chunk.requested_end_date)
        for chunk in chunks
    ] == [
        (date(2016, 2, 29), date(2026, 2, 27)),
        (date(2026, 2, 28), date(2026, 3, 2)),
    ]


def test_registry_semantics_remain_distinct() -> None:
    target = get_bcb_series(432)
    effective = get_bcb_series(1178)
    assert target.metric_id == "selic_target_annual"
    assert effective.metric_id == "selic_effective_annual_252"
    assert target.unit == effective.unit == "percent_per_year"
    assert target.display_name != effective.display_name
    assert "Copom" in target.display_name
    assert "252" in effective.display_name
