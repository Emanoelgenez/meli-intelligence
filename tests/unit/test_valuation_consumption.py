"""Offline contract tests for valuation snapshots consuming persisted Gold."""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.analytics.valuation import (
    STATUS_AVAILABLE,
    STATUS_CURRENCY_MISMATCH,
    STATUS_GOLD_MARKET_CAP_UNAVAILABLE,
    STATUS_INVALID_DENOMINATOR,
    STATUS_LOOKAHEAD_PREVENTED,
    STATUS_MISSING_DENOMINATOR,
    STATUS_NO_ELIGIBLE_MARKET_CAP,
    STATUS_PERIOD_MISMATCH,
    STATUS_UNSUPPORTED_TICKER,
    VALUATION_STATUSES,
    build_valuation_snapshot,
    select_financial_fact_as_of,
    select_market_cap_gold_as_of,
)
from meli_intelligence.storage.market_cap import read_market_cap_gold, write_market_cap_gold


MARKET_REFERENCE_DATE = date(2026, 10, 5)
VALUATION_REFERENCE_DATE = date(2026, 10, 7)
PRICE = 1860.60999
SHARES = 50_696_802
MARKET_CAP = PRICE * SHARES


def _gold_row(
    reference_date=MARKET_REFERENCE_DATE,
    *,
    value=MARKET_CAP,
    status="AVAILABLE",
    currency="USD",
    ticker="MELI",
):
    available = status == "AVAILABLE"
    return {
        "ticker": ticker,
        "entity": "MercadoLibre, Inc.",
        "reference_date": reference_date,
        "value": value if available else None,
        "currency": currency,
        "status": status,
        "reason": None if available else "Synthetic unavailable Gold input.",
        "price": PRICE if available else None,
        "shares_outstanding": SHARES if available else None,
        "shares_reference_date": date(2026, 8, 5) if available else None,
        "shares_filed_at": date(2026, 8, 6) if available else None,
        "shares_accession_number": "0001099590-26-000023" if available else None,
        "source_metric_ids": "market:close;dei:EntityCommonStockSharesOutstanding" if available else "",
        "market_source": "Twelve Data",
        "market_source_url": "https://api.twelvedata.com/time_series?symbol=MELI&interval=1day&adjust=none",
        "market_retrieved_at": "2026-10-06T12:00:00+00:00",
        "market_source_bronze_file": "market/meli.json" if available else None,
        "market_source_content_sha256": "a" * 64 if available else None,
        "shares_source": "SEC EDGAR Company Facts API" if available else None,
        "shares_source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001099590.json" if available else None,
        "methodology_version": "1",
    }


def _equity(value=10_000_000_000, *, period_end="2026-09-30", filed_at="2026-10-06", accession="equity-1"):
    return {
        "metric_id": "stockholders_equity",
        "value": value,
        "unit": "USD",
        "period_start": None,
        "period_end": period_end,
        "period_type": "INSTANT",
        "filed_at": filed_at,
        "accession_number": accession,
        "is_derived": False,
    }


def _persisted_gold(tmp_path, rows):
    path = tmp_path / "gold" / "market" / "market_capitalization.parquet"
    write_market_cap_gold(pd.DataFrame(rows), path=path)
    return read_market_cap_gold(path)


def test_latest_eligible_available_gold_is_selected_and_future_is_excluded():
    gold = pd.DataFrame([
        _gold_row(date(2026, 10, 3), value=90_000_000_000.0),
        _gold_row(date(2026, 10, 5)),
        _gold_row(date(2026, 10, 8), value=99_000_000_000.0),
    ])
    selected = select_market_cap_gold_as_of(gold, valuation_reference_date=VALUATION_REFERENCE_DATE)
    assert selected.reference_date == MARKET_REFERENCE_DATE
    assert selected.value == MARKET_CAP
    assert selected.status == STATUS_AVAILABLE
    assert selected.methodology_version == "1"


def test_future_gold_observation_and_exact_reference_date_are_not_looked_ahead():
    future = pd.DataFrame([_gold_row(date(2026, 10, 6))])
    selected = select_market_cap_gold_as_of(future, valuation_reference_date=MARKET_REFERENCE_DATE)
    assert selected.status == STATUS_NO_ELIGIBLE_MARKET_CAP
    assert selected.value is None
    assert selected.reference_date is None


@pytest.mark.parametrize("field", ["shares_reference_date", "shares_filed_at"])
def test_gold_with_future_share_count_provenance_is_not_consumed(field):
    row = _gold_row()
    row[field] = date(2026, 10, 6)
    selected = select_market_cap_gold_as_of(
        pd.DataFrame([row]), valuation_reference_date=VALUATION_REFERENCE_DATE,
    )
    assert selected.status == STATUS_LOOKAHEAD_PREVENTED
    assert selected.value is None


def test_latest_unavailable_gold_row_does_not_fall_back_to_older_available_value():
    gold = pd.DataFrame([
        _gold_row(date(2026, 10, 4), value=90_000_000_000.0),
        _gold_row(MARKET_REFERENCE_DATE, status="UNAVAILABLE_MISSING_SHARE_COUNT"),
    ])
    snapshot = build_valuation_snapshot(gold, pd.DataFrame([_equity()]), valuation_reference_date=VALUATION_REFERENCE_DATE)
    assert snapshot.market_cap.reference_date == MARKET_REFERENCE_DATE
    assert snapshot.market_cap.status == STATUS_GOLD_MARKET_CAP_UNAVAILABLE
    assert snapshot.market_cap.gold_status == "UNAVAILABLE_MISSING_SHARE_COUNT"
    assert snapshot.market_cap.value is None
    assert all(metric.value is None for metric in snapshot.metrics)


def test_meli_usd_guard_is_preserved():
    unsupported = select_market_cap_gold_as_of(
        pd.DataFrame([_gold_row(ticker="MELI34")]), valuation_reference_date=VALUATION_REFERENCE_DATE,
    )
    mismatch = select_market_cap_gold_as_of(
        pd.DataFrame([_gold_row(currency="BRL")]), valuation_reference_date=VALUATION_REFERENCE_DATE,
    )
    assert unsupported.status == STATUS_UNSUPPORTED_TICKER
    assert mismatch.status == STATUS_CURRENCY_MISMATCH
    assert unsupported.value is None and mismatch.value is None


def test_snapshot_consumes_persisted_gold_and_uses_requested_valuation_date(tmp_path):
    persisted = _persisted_gold(tmp_path, [_gold_row()])
    facts = pd.DataFrame([_equity(accession="equity-filed-before-valuation-date")])
    snapshot = build_valuation_snapshot(
        persisted, facts, valuation_reference_date=VALUATION_REFERENCE_DATE,
    )
    pb = {item.metric_id: item for item in snapshot.metrics}["price_to_book"]
    assert snapshot.valuation_reference_date == VALUATION_REFERENCE_DATE
    assert snapshot.market_cap.reference_date == MARKET_REFERENCE_DATE
    assert snapshot.market_cap.value == MARKET_CAP
    assert pb.reference_date == VALUATION_REFERENCE_DATE
    assert pb.status == STATUS_AVAILABLE
    assert pb.value == MARKET_CAP / 10_000_000_000


def test_equity_selector_reuses_instant_and_filed_by_date_rules():
    facts = pd.DataFrame([
        _equity(9_000_000_000, filed_at="2026-10-08", accession="future-filed"),
        _equity(10_000_000_000, filed_at="2026-10-06", accession="eligible"),
    ])
    selected = select_financial_fact_as_of(
        facts, metric_id="stockholders_equity", market_reference_date=VALUATION_REFERENCE_DATE,
    )
    assert selected is not None
    assert selected.value == 10_000_000_000
    assert selected.accession_number == "eligible"
    assert selected.period_type == "INSTANT"


def test_future_filed_equity_is_excluded_and_reported_as_lookahead_prevented():
    facts = pd.DataFrame([_equity(filed_at="2026-10-08", accession="future")])
    snapshot = build_valuation_snapshot(pd.DataFrame([_gold_row()]), facts,
                                       valuation_reference_date=VALUATION_REFERENCE_DATE)
    pb = {item.metric_id: item for item in snapshot.metrics}["price_to_book"]
    assert pb.status == STATUS_LOOKAHEAD_PREVENTED
    assert pb.value is None


def test_missing_equity_is_explicitly_unavailable():
    snapshot = build_valuation_snapshot(pd.DataFrame([_gold_row()]), None,
                                       valuation_reference_date=VALUATION_REFERENCE_DATE)
    pb = {item.metric_id: item for item in snapshot.metrics}["price_to_book"]
    assert pb.status == STATUS_MISSING_DENOMINATOR
    assert pb.value is None


@pytest.mark.parametrize("equity", [0, -1])
def test_nonpositive_book_value_is_invalid_not_a_multiple(equity):
    snapshot = build_valuation_snapshot(pd.DataFrame([_gold_row()]), pd.DataFrame([_equity(equity)]),
                                       valuation_reference_date=VALUATION_REFERENCE_DATE)
    pb = {item.metric_id: item for item in snapshot.metrics}["price_to_book"]
    assert pb.status == STATUS_INVALID_DENOMINATOR
    assert pb.value is None


def test_ps_and_pocf_remain_unavailable_without_a_ttm_contract_and_pe_is_absent():
    facts = pd.DataFrame([
        {
            "metric_id": "net_revenues_financial_income", "value": 100.0, "unit": "USD",
            "period_start": "2026-07-01", "period_end": "2026-09-30", "period_type": "QUARTER",
            "filed_at": "2026-10-06", "accession_number": "revenue-q", "is_derived": False,
        },
        {
            "metric_id": "operating_cash_flow", "value": 30.0, "unit": "USD",
            "period_start": "2026-07-01", "period_end": "2026-09-30", "period_type": "QUARTER",
            "filed_at": "2026-10-06", "accession_number": "ocf-q", "is_derived": False,
        },
    ])
    snapshot = build_valuation_snapshot(pd.DataFrame([_gold_row()]), facts,
                                       valuation_reference_date=VALUATION_REFERENCE_DATE)
    metrics = {item.metric_id: item for item in snapshot.metrics}
    assert metrics["price_to_sales"].status == STATUS_PERIOD_MISMATCH
    assert metrics["price_to_operating_cash_flow"].status == STATUS_PERIOD_MISMATCH
    assert metrics["price_to_sales"].value is None
    assert metrics["price_to_operating_cash_flow"].value is None
    assert "price_to_earnings" not in metrics


def test_market_and_financial_lineage_are_preserved():
    snapshot = build_valuation_snapshot(
        pd.DataFrame([_gold_row()]), pd.DataFrame([_equity()]),
        valuation_reference_date=VALUATION_REFERENCE_DATE,
    )
    pb = {item.metric_id: item for item in snapshot.metrics}["price_to_book"]
    assert snapshot.market_cap.source_metric_ids == (
        "market:close", "dei:EntityCommonStockSharesOutstanding",
    )
    assert pb.source_metric_ids == (
        "dei:EntityCommonStockSharesOutstanding", "market:close", "stockholders_equity",
    )
    assert pb.source_accession_numbers == ("0001099590-26-000023", "equity-1")


def test_result_is_deterministic_and_has_explicit_unavailable_states():
    gold = pd.DataFrame([_gold_row()])
    facts = pd.DataFrame([_equity()])
    first = build_valuation_snapshot(gold, facts, valuation_reference_date=VALUATION_REFERENCE_DATE)
    second = build_valuation_snapshot(gold, facts, valuation_reference_date=VALUATION_REFERENCE_DATE)
    assert first == second
    assert all(metric.status in VALUATION_STATUSES for metric in first.metrics)


def test_valuation_consumption_has_no_product_network_or_repository_data_dependency():
    path = Path(__file__).resolve().parents[2] / "src/meli_intelligence/analytics/valuation.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any("product" in module.lower() or module.startswith("httpx") for module in imports)
    assert '"data/' not in source.replace("\\", "/")


def test_empty_gold_snapshot_is_explicit_and_never_emits_numeric_multiple():
    snapshot = build_valuation_snapshot(None, pd.DataFrame([_equity()]),
                                       valuation_reference_date=VALUATION_REFERENCE_DATE)
    assert snapshot.market_cap.status == STATUS_NO_ELIGIBLE_MARKET_CAP
    assert snapshot.market_cap.value is None
    assert all(metric.value is None for metric in snapshot.metrics)
