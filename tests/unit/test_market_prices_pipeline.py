"""Offline tests for Twelve Data Bronze, Silver, incremental pipeline and UI contract."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import httpx
import pandas as pd
import pyarrow.parquet as pq
import pytest

from meli_intelligence.pipelines.market_prices import run_market_price_pipeline
from meli_intelligence.sources.market.twelve_data import TwelveDataClient
from meli_intelligence.storage.market_bronze import save_market_bronze
from meli_intelligence.storage.market_prices import (
    MARKET_PRICES_SCHEMA, merge_market_prices, read_market_prices, write_market_prices,
)
from meli_intelligence.transformations.market_prices import normalize_market_prices
from meli_intelligence.ui.market_storytelling import market_freshness, select_latest_market_price, select_market_trend

RAW = {
    "meta": {"symbol": "MELI", "interval": "1day", "currency": "USD", "exchange": "NASDAQ", "mic_code": "XNGS"},
    "values": [
        {"datetime": "2026-10-02", "open": "2000", "high": "2020", "low": "1990", "close": "2010", "volume": "1234"},
        {"datetime": "2026-10-05", "open": "2011", "high": "2030", "low": "2000", "close": "2025", "volume": "1400"},
    ],
}


def _fetch(raw=RAW, retrieved="2026-10-06T12:00:00+00:00"):
    encoded = json.dumps(raw, separators=(",", ":")).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=encoded, headers={"content-type": "application/json"}))
    client = TwelveDataClient(transport=transport, api_key="offline" + "-test-" + "key")
    fetched = client.fetch_daily(outputsize=100)
    return fetched.__class__(fetched.raw_payload, fetched.payload, retrieved, fetched.source_url,
                             fetched.requested_start_date, fetched.requested_end_date, fetched.outputsize)


def _frame(tmp_path: Path, raw=RAW):
    fetched = _fetch(raw)
    raw_path, _, digest = save_market_bronze(fetched, bronze_dir=tmp_path / "bronze")
    return normalize_market_prices(fetched, source_bronze_file=raw_path.name, source_content_sha256=digest)


def test_bronze_raw_provenance_hash_and_replay_are_safe(tmp_path):
    fetched = _fetch()
    raw_path, metadata_path, digest = save_market_bronze(fetched, bronze_dir=tmp_path)
    assert raw_path.read_bytes() == fetched.raw_payload
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["provider"] == "Twelve Data" and metadata["requested_ticker"] == "MELI"
    assert metadata["retrieved_at"] == fetched.retrieved_at
    assert metadata["payload_sha256"] == hashlib.sha256(fetched.raw_payload).hexdigest() == digest
    assert "apikey" not in metadata["source_url"].lower()
    assert "apikey" not in metadata["source_url"].lower()
    assert save_market_bronze(fetched, bronze_dir=tmp_path)[0] == raw_path


def test_silver_roundtrip_schema_zstd_and_contract(tmp_path):
    frame = _frame(tmp_path)
    path, metadata = write_market_prices(frame, output_path=tmp_path / "market" / "market_prices.parquet")
    restored = read_market_prices(path)
    assert metadata.exists() and list(restored.columns) == MARKET_PRICES_SCHEMA.names
    assert restored.reference_date.tolist() == [date(2026, 10, 2), date(2026, 10, 5)]
    assert restored.ticker.eq("MELI").all() and restored.entity.eq("MercadoLibre, Inc.").all()
    assert restored.close.tolist() == [2010.0, 2025.0]
    assert pq.ParquetFile(path).metadata.row_group(0).column(0).compression == "ZSTD"


def test_missing_volume_remains_nullable_not_zero(tmp_path):
    raw = {**RAW, "values": [{key: value for key, value in RAW["values"][0].items() if key != "volume"}]}
    frame = _frame(tmp_path, raw)
    assert pd.isna(frame.volume.iloc[0])
    path, _ = write_market_prices(frame, output_path=tmp_path / "no-volume.parquet")
    restored = read_market_prices(path)
    assert pd.isna(restored.volume.iloc[0])


def test_incremental_merge_preserves_history_and_is_idempotent(tmp_path):
    older = _frame(tmp_path)
    newer_raw = {**RAW, "values": [dict(RAW["values"][1]), {
        "datetime": "2026-10-06", "open": "2026", "high": "2040", "low": "2020", "close": "2035", "volume": "1500"}]}
    newer = _frame(tmp_path / "second", newer_raw)
    merged = merge_market_prices(older, newer)
    assert len(merged) == 3 and date(2026, 10, 2) in set(merged.reference_date)
    assert len(merge_market_prices(merged, newer)) == 3
    assert list(merged.reference_date) == sorted(merged.reference_date)
    conflicting_raw = {**RAW, "values": [dict(RAW["values"][1], close="2026")]}
    conflicting = _frame(tmp_path / "third", conflicting_raw)
    with pytest.raises(ValueError, match="conflicts with stored"):
        merge_market_prices(merged, conflicting)


def test_ui_compatibility_uses_only_real_trading_dates(tmp_path):
    frame = _frame(tmp_path)
    latest = select_latest_market_price(frame)
    trend = select_market_trend(frame)
    assert latest.ticker == "MELI" and latest.currency == "USD" and latest.close == 2025.0
    assert latest.reference_date == date(2026, 10, 5)
    assert market_freshness(frame) == latest.reference_date
    assert trend.reference_date.tolist() == [pd.Timestamp("2026-10-02"), pd.Timestamp("2026-10-05")]
    assert not {"return", "market_cap", "pe", "ev_ebitda"}.intersection(trend.columns)


def test_pipeline_fake_response_is_idempotent_and_summarizes_without_secret(tmp_path):
    encoded = json.dumps(RAW, separators=(",", ":")).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=encoded, headers={"content-type": "application/json"}))
    client = TwelveDataClient(transport=transport, api_key="offline" + "-test-" + "key")
    silver = tmp_path / "silver" / "market_prices.parquet"
    first = run_market_price_pipeline(client=client, bronze_dir=tmp_path / "bronze", silver_path=silver)
    second = run_market_price_pipeline(client=client, bronze_dir=tmp_path / "bronze", silver_path=silver)
    assert first.rows_received == 2 and first.rows_written == 2
    assert second.rows_written == 0
    assert first.content_sha256 == hashlib.sha256(encoded).hexdigest()
    assert ("offline" + "-test-" + "key") not in repr(first)
    assert len(read_market_prices(silver)) == 2


def test_incremental_recent_window_never_truncates_old_rows(tmp_path):
    history = _frame(tmp_path)
    path = tmp_path / "silver.parquet"
    write_market_prices(history, output_path=path)
    recent = history.iloc[[-1]].copy()
    merged = merge_market_prices(read_market_prices(path), recent)
    assert len(merged) == 2
    assert date(2026, 10, 2) in set(merged.reference_date)
