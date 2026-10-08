"""Offline Gold market-cap analytics and storage tests."""
from __future__ import annotations

import ast
from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.analytics.market_cap import (
    ENTITY,
    SEC_CONCEPT,
    SEC_METRIC_ID,
    SEC_SOURCE,
    STATUS_AVAILABLE,
    STATUS_CURRENCY_MISMATCH,
    STATUS_MISSING_SHARE_COUNT,
    STATUS_UNSUPPORTED_TICKER,
    build_market_cap_gold,
)
from meli_intelligence.storage.market_cap import (
    MARKET_CAP_SCHEMA,
    _prepare,
    merge_market_cap_gold,
    read_market_cap_gold,
    write_market_cap_gold,
)
from meli_intelligence.storage.shares_outstanding import write_shares_outstanding
from meli_intelligence.transformations.sec_companyfacts import normalize_shares_outstanding


def _share_payload() -> dict:
    return {
        "cik": 1099590,
        "entityName": ENTITY,
        "facts": {"dei": {SEC_CONCEPT: {"units": {"shares": [
            {"end": "2026-05-07", "val": 50_697_182, "filed": "2026-05-08",
             "accn": "0001099590-26-000017", "form": "10-Q"},
            {"end": "2026-08-05", "val": 50_696_802, "filed": "2026-08-06",
             "accn": "0001099590-26-000023", "form": "10-Q"},
            {"end": "2026-09-30", "val": 50_000_000, "filed": "2026-10-07",
             "accn": "0001099590-26-000030", "form": "10-Q"},
            {"end": "2026-08-05", "val": 49_000_000, "filed": "2026-10-07",
             "accn": "0001099590-26-000031", "form": "10-Q"},
        ]}}}},
    }


def _market(*, ticker="MELI", currency="USD", reference=date(2026, 10, 5), price=1860.60999):
    return pd.DataFrame([{
        "ticker": ticker, "entity": ENTITY, "reference_date": reference,
        "open": price, "high": price, "low": price, "close": price,
        "volume": 1000.0, "currency": currency, "exchange": "NASDAQ",
        "mic_code": "XNGS", "source": "Twelve Data",
        "source_url": "https://api.twelvedata.com/time_series?symbol=MELI&interval=1day&adjust=none",
        "retrieved_at": "2026-10-06T12:00:00+00:00",
        "source_bronze_file": "bronze/meli.json",
        "source_content_sha256": "a" * 64,
    }])


def test_gold_uses_latest_eligible_shares_and_preserves_lineage():
    shares = normalize_shares_outstanding(_share_payload())
    original = _market()
    result = build_market_cap_gold(original, shares)
    row = result.iloc[0]
    assert row.status == STATUS_AVAILABLE
    assert row.shares_reference_date == date(2026, 8, 5)
    assert row.shares_filed_at == date(2026, 8, 6)
    assert row.shares_accession_number == "0001099590-26-000023"
    assert row.shares_outstanding == 50_696_802
    assert row.value == 1860.60999 * 50_696_802
    assert row.market_source_bronze_file == "bronze/meli.json"
    assert row.source_metric_ids == f"market:close;{SEC_METRIC_ID}"
    pd.testing.assert_frame_equal(original, _market())


def test_future_reference_and_future_filing_are_excluded_from_gold():
    facts = normalize_shares_outstanding(_share_payload())
    result = build_market_cap_gold(_market(), facts).iloc[0]
    assert result.status == STATUS_AVAILABLE
    assert result.shares_accession_number == "0001099590-26-000023"
    assert result.shares_reference_date < result.reference_date
    assert result.shares_filed_at <= result.reference_date


def test_missing_shares_is_unavailable_and_never_a_synthetic_zero():
    result = build_market_cap_gold(_market(), None).iloc[0]
    assert result.status == STATUS_MISSING_SHARE_COUNT
    assert pd.isna(result.value)


@pytest.mark.parametrize(
    ("market", "expected"),
    [(_market(ticker="MELI34"), STATUS_UNSUPPORTED_TICKER),
     (_market(currency="BRL"), STATUS_CURRENCY_MISMATCH)],
)
def test_gold_keeps_ticker_and_currency_guards(market, expected):
    result = build_market_cap_gold(market, normalize_shares_outstanding(_share_payload())).iloc[0]
    assert result.status == expected
    assert pd.isna(result.value)


def test_gold_storage_round_trip_and_idempotent_replay(tmp_path):
    facts = normalize_shares_outstanding(_share_payload())
    result = build_market_cap_gold(_market(), facts)
    path = tmp_path / "gold" / "market" / "market_capitalization.parquet"
    parquet_path, metadata_path = write_market_cap_gold(result, path=path)
    assert parquet_path.exists() and metadata_path.exists()
    first = read_market_cap_gold(path)
    first_parquet_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    first_metadata_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    generated_at = json.loads(metadata_path.read_text(encoding="utf-8"))["generated_at"]
    replay_parquet, replay_metadata = write_market_cap_gold(result, path=path)
    second = read_market_cap_gold(path)
    pd.testing.assert_frame_equal(first, second)
    assert replay_parquet == path and replay_metadata == metadata_path
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first_parquet_hash
    assert hashlib.sha256(metadata_path.read_bytes()).hexdigest() == first_metadata_hash
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["generated_at"] == generated_at
    assert len(second) == 1


def test_gold_nullable_strings_have_schema_driven_dtype_through_read_and_merge(tmp_path):
    first = _prepare(build_market_cap_gold(_market(), normalize_shares_outstanding(_share_payload())))
    assert tuple(first.columns) == tuple(MARKET_CAP_SCHEMA.names)
    assert first.reason.dtype == object
    assert first.reason.iloc[0] is None
    path = tmp_path / "gold" / "market" / "nullable.parquet"
    write_market_cap_gold(first, path=path)
    persisted = read_market_cap_gold(path)
    replay_merged = merge_market_cap_gold(persisted, first)
    assert persisted.reason.dtype == object
    assert replay_merged.reason.dtype == object
    assert replay_merged.reason.iloc[0] is None
    pd.testing.assert_frame_equal(first, replay_merged)


def test_new_gold_observation_changes_artifact_and_row_count(tmp_path):
    facts = normalize_shares_outstanding(_share_payload())
    initial = build_market_cap_gold(_market(), facts)
    path = tmp_path / "gold" / "market" / "incremental.parquet"
    _, metadata_path = write_market_cap_gold(initial, path=path)
    old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata_before = json.loads(metadata_path.read_text(encoding="utf-8"))

    next_market = pd.concat([
        _market(),
        _market(reference=date(2026, 10, 6), price=1870.0),
    ], ignore_index=True)
    expanded = build_market_cap_gold(next_market, facts)
    write_market_cap_gold(expanded, path=path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() != old_hash
    assert len(read_market_cap_gold(path)) == 2
    metadata_after = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata_before["row_count"] == 1
    assert metadata_after["row_count"] == 2


def test_gold_output_order_is_deterministic_when_market_input_is_reversed():
    facts = normalize_shares_outstanding(_share_payload())
    market = pd.concat([
        _market(reference=date(2026, 10, 6), price=1870.0),
        _market(reference=date(2026, 10, 5)),
    ], ignore_index=True)
    result = build_market_cap_gold(market, facts)
    assert result.reference_date.tolist() == [date(2026, 10, 5), date(2026, 10, 6)]


def test_gold_storage_preserves_explicit_unavailable_rows_without_zero(tmp_path):
    result = build_market_cap_gold(_market(), None)
    path = tmp_path / "gold" / "market" / "unavailable.parquet"
    write_market_cap_gold(result, path=path)
    loaded = read_market_cap_gold(path)
    assert loaded.iloc[0].status == "UNAVAILABLE_MISSING_SHARE_COUNT"
    assert pd.isna(loaded.iloc[0].value)


def test_conflicting_gold_result_for_same_market_key_fails():
    facts = normalize_shares_outstanding(_share_payload())
    result = build_market_cap_gold(_market(), facts)
    conflicting = result.copy()
    conflicting.loc[0, "price"] += 1
    conflicting.loc[0, "value"] = conflicting.loc[0, "price"] * conflicting.loc[0, "shares_outstanding"]
    with pytest.raises(ValueError, match="Conflicting Market Cap Gold"):
        merge_market_cap_gold(result, conflicting)


def test_analytics_gold_has_no_product_or_network_dependency_or_local_data_path():
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "src/meli_intelligence/analytics/market_cap.py",
        root / "src/meli_intelligence/storage/market_cap.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        assert not any("product" in module.lower() or module.startswith("httpx") for module in modules)
        assert "data/" not in path.read_text(encoding="utf-8").replace("\\", "/")


def test_silver_writer_accepts_normalizer_rows_without_remapping(tmp_path):
    path = tmp_path / "silver" / "shares.parquet"
    write_shares_outstanding(normalize_shares_outstanding(_share_payload()), path=path)
    loaded = pd.read_parquet(path)
    assert loaded.iloc[0].source_metric_id == SEC_METRIC_ID
    assert loaded.iloc[0].source == SEC_SOURCE
