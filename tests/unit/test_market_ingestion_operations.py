"""Offline operational boundary, dry-run and completed-session protections."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys

import pandas as pd
import pytest

from meli_intelligence.pipelines import market_prices as pipeline
from meli_intelligence.sources.market.twelve_data import TwelveDataFetch, sanitized_source_url, build_request_params
from meli_intelligence.storage.market_bronze import save_market_bronze
from meli_intelligence.storage.market_prices import read_market_prices, write_market_prices
from meli_intelligence.transformations.market_prices import normalize_market_prices

NY = "America/New_York"
META = {"symbol": "MELI", "interval": "1day", "currency": "USD", "exchange": "NASDAQ", "mic_code": "XNGS"}


def fetch_for(day: str, *, retrieved: str = "2026-10-06T14:00:00+00:00", close: str = "2025"):
    values = [{"datetime": day, "open": "2010", "high": "2030", "low": "2000", "close": close, "volume": "100"}]
    payload = {"meta": META, "values": values}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    request = build_request_params(outputsize=100)
    return TwelveDataFetch(raw, payload, retrieved, sanitized_source_url(request), None, None, 100)


class FakeClient:
    def __init__(self, fetch):
        self.fetch = fetch
        self.calls = []

    def fetch_daily(self, **kwargs):
        self.calls.append(kwargs)
        return self.fetch


def test_safe_boundary_converts_aware_instants_to_new_york_civil_date():
    assert pipeline.MARKET_EXCHANGE_TIMEZONE == NY
    assert pipeline.resolve_completed_session_boundary(
        now=datetime(2026, 10, 6, 12, tzinfo=timezone.utc),
    ) == date(2026, 10, 6)
    # UTC has crossed midnight; New York has not.
    assert pipeline.resolve_completed_session_boundary(
        now=datetime(2026, 10, 7, 2, tzinfo=timezone.utc),
    ) == date(2026, 10, 6)
    assert pipeline.resolve_completed_session_boundary(
        now=datetime(2026, 10, 7, 4, 5, tzinfo=timezone.utc),
    ) == date(2026, 10, 7)


def test_naive_clock_rejected_and_weekend_boundary_not_shifted():
    with pytest.raises(ValueError, match="timezone-aware"):
        pipeline.resolve_completed_session_boundary(now=datetime(2026, 10, 6, 12))
    saturday = datetime(2026, 10, 10, 12, tzinfo=pipeline.MARKET_TIMEZONE)
    assert pipeline.resolve_completed_session_boundary(now=saturday) == date(2026, 10, 10)


def test_plan_defaults_to_safe_boundary_and_accepts_historical_or_equal_dates():
    now = datetime(2026, 10, 6, 14, tzinfo=timezone.utc)
    plan = pipeline.build_market_ingestion_plan(now=now)
    assert plan.end_date == plan.safe_boundary_date == date(2026, 10, 6)
    assert plan.timezone == NY and plan.endpoint.endswith("/time_series")
    old = pipeline.build_market_ingestion_plan(end_date="2026-10-03", now=now)
    assert old.end_date == date(2026, 10, 3)
    equal = pipeline.build_market_ingestion_plan(end_date=date(2026, 10, 6), now=now)
    assert equal.end_date == date(2026, 10, 6)
    with pytest.raises(ValueError, match="later than the current"):
        pipeline.build_market_ingestion_plan(end_date="2026-10-07", now=now)
    with pytest.raises(ValueError, match="start_date"):
        pipeline.build_market_ingestion_plan(start_date="2026-10-07", now=now)


def test_default_pipeline_requests_safe_boundary_and_summary_reports_plan(tmp_path):
    client = FakeClient(fetch_for("2026-10-05"))
    summary = pipeline.run_market_price_pipeline(
        client=client, now=datetime(2026, 10, 6, 13, tzinfo=timezone.utc),
        bronze_dir=tmp_path / "bronze", silver_path=tmp_path / "silver.parquet",
    )
    assert client.calls[0]["end_date"] == date(2026, 10, 6)
    assert summary.requested_end_date == summary.safe_boundary_date == "2026-10-06"
    assert summary.latest_reference_date == "2026-10-05"


def test_future_end_date_rejected_before_fake_client_or_filesystem(tmp_path):
    client = FakeClient(fetch_for("2026-10-05"))
    with pytest.raises(ValueError, match="later than the current"):
        pipeline.run_market_price_pipeline(
            end_date="2026-10-07", client=client,
            now=datetime(2026, 10, 6, 14, tzinfo=timezone.utc),
            bronze_dir=tmp_path / "bronze", silver_path=tmp_path / "silver.parquet",
        )
    assert client.calls == []
    assert not list(tmp_path.iterdir())


def test_dry_run_cli_needs_no_key_http_or_filesystem(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["market_prices", "--dry-run", "--start-date", "2026-10-01"])
    monkeypatch.setattr(pipeline, "TwelveDataClient", lambda: (_ for _ in ()).throw(AssertionError("client constructed")))
    pipeline.main()
    output = capsys.readouterr().out
    assert "Provider: Twelve Data" in output
    assert "Ticker: MELI" in output and "Interval: 1day" in output
    assert "Safe boundary: " in output and "Start date: 2026-10-01" in output
    assert "Network: disabled (dry-run)" in output and "Writes: disabled (dry-run)" in output
    assert "apikey" not in output.lower() and "TWELVE_DATA_API_KEY" not in output
    assert list(tmp_path.iterdir()) == []


def test_pipeline_without_key_still_fails_before_http_or_writes(monkeypatch, tmp_path):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TWELVE_DATA_API_KEY is required"):
        pipeline.run_market_price_pipeline(
            now=datetime(2026, 10, 6, 14, tzinfo=timezone.utc),
            bronze_dir=tmp_path / "bronze", silver_path=tmp_path / "silver.parquet",
        )
    assert list(tmp_path.iterdir()) == []


def test_current_or_later_session_is_rejected_after_bronze_before_silver_write(tmp_path):
    silver = tmp_path / "silver.parquet"
    older_fetch = fetch_for("2026-10-05", retrieved="2026-10-06T12:00:00+00:00")
    bronze_old, _, digest_old = save_market_bronze(older_fetch, bronze_dir=tmp_path / "initial-bronze")
    old_frame = normalize_market_prices(older_fetch, source_bronze_file=bronze_old.name, source_content_sha256=digest_old)
    write_market_prices(old_frame, output_path=silver)
    old_bytes = silver.read_bytes()

    current_fetch = fetch_for("2026-10-06", retrieved="2026-10-06T15:00:00+00:00")
    client = FakeClient(current_fetch)
    with pytest.raises(ValueError, match="at/after the safe boundary"):
        pipeline.run_market_price_pipeline(
            client=client, now=datetime(2026, 10, 6, 15, tzinfo=timezone.utc),
            bronze_dir=tmp_path / "violating-bronze", silver_path=silver,
        )
    raw_files = [path for path in (tmp_path / "violating-bronze").glob("*.json") if not path.name.endswith(".metadata.json")]
    assert len(raw_files) == 1
    assert silver.read_bytes() == old_bytes
    assert len(read_market_prices(silver)) == 1


def test_same_day_rerun_can_write_zero_silver_rows_but_preserves_each_fetch_bronze(tmp_path):
    class SequentialClient:
        def __init__(self):
            self.index = 0

        def fetch_daily(self, **kwargs):
            stamp = ("2026-10-06T14:00:00+00:00", "2026-10-06T15:00:00+00:00")[self.index]
            self.index += 1
            return fetch_for("2026-10-05", retrieved=stamp)

    silver = tmp_path / "silver.parquet"
    bronze = tmp_path / "bronze"
    client = SequentialClient()
    now = datetime(2026, 10, 6, 15, tzinfo=timezone.utc)
    first = pipeline.run_market_price_pipeline(client=client, now=now, bronze_dir=bronze, silver_path=silver)
    second = pipeline.run_market_price_pipeline(client=client, now=now, bronze_dir=bronze, silver_path=silver)
    assert first.rows_received > 0 and first.rows_written == 1
    assert second.rows_received > 0 and second.rows_written == 0
    assert len(read_market_prices(silver)) == 1
    raw_files = [path for path in bronze.glob("*.json") if not path.name.endswith(".metadata.json")]
    assert len(raw_files) == 2
    assert len(list(bronze.glob("*.metadata.json"))) == 2
