"""Offline tests for authoritative share-count alignment and market cap."""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.analytics.market_cap import (
    ENTITY,
    SEC_CONCEPT,
    SEC_METRIC_ID,
    SEC_SOURCE,
    SEC_TAXONOMY,
    STATUS_AVAILABLE,
    STATUS_CURRENCY_MISMATCH,
    STATUS_INVALID_PRICE,
    STATUS_INVALID_SHARE_COUNT,
    STATUS_LOOKAHEAD,
    STATUS_MISSING_SHARE_COUNT,
    STATUS_UNSUPPORTED_TICKER,
    calculate_market_cap,
    select_shares_outstanding_as_of,
    SharesOutstandingFact,
)
from meli_intelligence.analytics.valuation import (
    STATUS_MISSING_MARKET_CAP,
    STATUS_PERIOD_MISMATCH,
    build_valuation_availability,
)
from meli_intelligence.transformations.sec_companyfacts import normalize_shares_outstanding


def _share_fact(value=50_000_000, *, reference="2025-12-31", filed="2026-02-20", accession="0001"):
    return {
        "entity": ENTITY,
        "metric_id": "shares_outstanding",
        "source_metric_id": SEC_METRIC_ID,
        "taxonomy": SEC_TAXONOMY,
        "concept": SEC_CONCEPT,
        "reference_date": reference,
        "value": value,
        "unit": "shares",
        "filed_at": filed,
        "accession_number": accession,
        "form": "10-K",
        "source": SEC_SOURCE,
        "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001099590.json",
    }


def _cap(**kwargs):
    return calculate_market_cap(
        ticker=kwargs.pop("ticker", "MELI"),
        price=kwargs.pop("price", 2000.0),
        currency=kwargs.pop("currency", "USD"),
        market_reference_date=kwargs.pop("market_reference_date", date(2026, 3, 1)),
        shares_facts=kwargs.pop("shares_facts", [_share_fact()]),
    )


def _fact_object(
    value=50_000_000, *, reference=date(2025, 12, 31), filed=date(2026, 2, 20),
    accession="0001", source="SEC Company Facts",
):
    return SharesOutstandingFact(
        entity=ENTITY,
        value=float(value),
        reference_date=reference,
        filed_at=filed,
        accession_number=accession,
        source=source,
        source_metric_id=SEC_METRIC_ID,
        unit="shares",
        taxonomy="dei",
        concept=SEC_CONCEPT,
        form="10-Q",
        source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0001099590.json",
    )


def test_no_authoritative_shares_is_explicitly_unavailable():
    result = _cap(shares_facts=None)
    assert result.value is None
    assert result.status == STATUS_MISSING_SHARE_COUNT


def test_future_filed_shares_are_not_used_and_report_lookahead():
    fact = _share_fact(reference="2025-12-31", filed="2026-03-02")
    result = _cap(market_reference_date=date(2026, 3, 1), shares_facts=[fact])
    assert result.value is None
    assert result.status == STATUS_LOOKAHEAD


def test_latest_eligible_fact_is_selected_deterministically():
    older = _share_fact(49_000_000, reference="2025-09-30", filed="2025-11-01", accession="a")
    newer_low_accn = _share_fact(50_000_000, reference="2025-12-31", filed="2026-02-20", accession="0001")
    newer_high_accn = _share_fact(51_000_000, reference="2025-12-31", filed="2026-02-20", accession="0002")
    selected = select_shares_outstanding_as_of(
        [newer_low_accn, older, newer_high_accn], market_reference_date=date(2026, 3, 1),
    )
    assert selected is not None
    assert selected.value == 51_000_000
    assert selected.accession_number == "0002"


def test_iterable_of_live_shaped_share_fact_dataclasses_is_selected():
    live_fact = _fact_object(
        50_696_802.0,
        reference=date(2026, 8, 5),
        filed=date(2026, 8, 6),
        accession="0001099590-26-000023",
    )
    selected = select_shares_outstanding_as_of(
        [live_fact], market_reference_date=date(2026, 10, 5),
    )
    assert selected == live_fact
    assert selected.reference_date == date(2026, 8, 5)
    assert selected.filed_at == date(2026, 8, 6)
    assert selected.value == 50_696_802.0
    assert selected.accession_number == "0001099590-26-000023"


def test_market_cap_reproduces_live_shaped_scenario_by_exact_formula():
    price = 1860.60999
    shares = 50_696_802.0
    fact = _fact_object(
        shares,
        reference=date(2026, 8, 5),
        filed=date(2026, 8, 6),
        accession="0001099590-26-000023",
    )
    result = calculate_market_cap(
        ticker="MELI", price=price, currency="USD",
        market_reference_date=date(2026, 10, 5), shares_facts=[fact],
    )
    assert result.status == STATUS_AVAILABLE
    assert result.value == price * shares
    assert result.shares_outstanding == shares


def test_future_reference_date_is_excluded_while_latest_eligible_is_kept():
    eligible = _fact_object(50_696_802, reference=date(2026, 8, 5), filed=date(2026, 8, 6), accession="eligible")
    future = _fact_object(50_000_000, reference=date(2026, 10, 6), filed=date(2026, 10, 6), accession="future")
    selected = select_shares_outstanding_as_of(
        [future, eligible], market_reference_date=date(2026, 10, 5),
    )
    assert selected == eligible


def test_future_filed_at_is_excluded_even_if_reference_date_is_eligible():
    eligible = _fact_object(50_000_000, reference=date(2026, 5, 7), filed=date(2026, 5, 8), accession="eligible")
    future_filed = _fact_object(50_696_802, reference=date(2026, 8, 5), filed=date(2026, 10, 6), accession="future-filed")
    selected = select_shares_outstanding_as_of(
        [future_filed, eligible], market_reference_date=date(2026, 10, 5),
    )
    assert selected == eligible


def test_sec_normalizer_output_feeds_public_selector_without_remapping():
    payload = {
        "cik": 1099590,
        "entityName": ENTITY,
        "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2026-08-05", "val": 50_696_802, "filed": "2026-08-06",
             "accn": "0001099590-26-000023", "form": "10-Q"},
            {"end": "2026-05-07", "val": 50_697_182, "filed": "2026-05-08",
             "accn": "0001099590-26-000017", "form": "10-Q"},
            {"end": "2026-02-25", "val": 50_697_182, "filed": "2026-02-25",
             "accn": "0001099590-26-000006", "form": "10-K"},
        ]}}}},
    }
    normalized = normalize_shares_outstanding(payload)
    selected = select_shares_outstanding_as_of(
        normalized, market_reference_date=date(2026, 10, 5),
    )
    assert selected is not None
    assert selected.reference_date == date(2026, 8, 5)
    assert selected.filed_at == date(2026, 8, 6)
    assert selected.value == 50_696_802.0
    assert selected.accession_number == "0001099590-26-000023"


def test_no_hard_coded_meli_share_count_in_production_sources():
    root = Path(__file__).resolve().parents[2]
    sources = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in (
            "src/meli_intelligence/analytics/market_cap.py",
            "src/meli_intelligence/transformations/sec_companyfacts.py",
        )
    ).lower()
    for literal in ("shares_outstanding = 50696802", "share_count = 50696802", "shares = 50696802"):
        assert literal not in sources


def test_exact_close_times_authoritative_shares_formula_and_usd_scope():
    result = _cap()
    assert result.status == STATUS_AVAILABLE
    assert result.value == 100_000_000_000
    assert result.currency == "USD"
    assert result.price == 2000.0
    assert result.shares_outstanding == 50_000_000
    assert result.source_metric_ids == ("market:close", SEC_METRIC_ID)


@pytest.mark.parametrize("price", [0, -1, float("inf"), float("nan"), None])
def test_invalid_price_is_never_converted_to_market_cap(price):
    result = _cap(price=price)
    assert result.value is None
    assert result.status == STATUS_INVALID_PRICE


@pytest.mark.parametrize("shares", [0, -1, float("inf"), float("nan")])
def test_invalid_shares_are_never_converted_to_market_cap(shares):
    result = _cap(shares_facts=[_share_fact(shares)])
    assert result.value is None
    assert result.status == STATUS_INVALID_SHARE_COUNT


def test_non_usd_price_is_rejected():
    assert _cap(currency="BRL").status == STATUS_CURRENCY_MISMATCH


@pytest.mark.parametrize("ticker", ["MELI34", "AAPL"])
def test_only_meli_market_instrument_is_supported(ticker):
    assert _cap(ticker=ticker).status == STATUS_UNSUPPORTED_TICKER


def test_tie_break_uses_accession_and_input_order_does_not_matter():
    facts = [
        _share_fact(51_000_000, accession="0002"),
        _share_fact(50_000_000, accession="0001"),
    ]
    a = select_shares_outstanding_as_of(facts, market_reference_date=date(2026, 3, 1))
    b = select_shares_outstanding_as_of(list(reversed(facts)), market_reference_date=date(2026, 3, 1))
    assert a == b
    assert a is not None and a.accession_number == "0002"


def test_unrecognized_or_non_sec_share_count_is_not_authoritative():
    guessed = _share_fact()
    guessed.update(source="third-party", taxonomy="custom", concept="EstimatedShares")
    assert _cap(shares_facts=[guessed]).status == STATUS_MISSING_SHARE_COUNT


def test_market_cap_code_has_no_product_or_network_dependency():
    root = Path(__file__).resolve().parents[2]
    path = root / "src" / "meli_intelligence" / "analytics" / "market_cap.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = [
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any("product" in module.lower() or module.startswith("httpx") for module in modules)


def test_valuation_requires_market_cap_and_only_enables_compatible_book_multiple():
    missing = build_valuation_availability()
    assert all(item.status == STATUS_MISSING_MARKET_CAP and item.value is None for item in missing)

    cap = _cap()
    facts = pd.DataFrame([{
        "metric_id": "stockholders_equity", "value": 10_000_000_000, "unit": "USD",
        "period_start": None, "period_end": date(2025, 12, 31), "period_type": "INSTANT",
        "filed_at": date(2026, 2, 20), "accession_number": "0001", "is_derived": False,
    }, {
        "metric_id": "net_revenues_financial_income", "value": 4_000_000_000, "unit": "USD",
        "period_start": date(2025, 10, 1), "period_end": date(2025, 12, 31), "period_type": "QUARTER",
        "filed_at": date(2026, 2, 20), "accession_number": "0002", "is_derived": False,
    }, {
        "metric_id": "operating_cash_flow", "value": 1_000_000_000, "unit": "USD",
        "period_start": date(2025, 10, 1), "period_end": date(2025, 12, 31), "period_type": "QUARTER",
        "filed_at": date(2026, 2, 20), "accession_number": "0003", "is_derived": False,
    }])
    metrics = {item.metric_id: item for item in build_valuation_availability(market_cap=cap, financial_facts=facts)}
    assert metrics["price_to_book"].status == STATUS_AVAILABLE
    assert metrics["price_to_book"].value == 10.0
    assert metrics["price_to_sales"].status == STATUS_PERIOD_MISMATCH
    assert metrics["price_to_operating_cash_flow"].status == STATUS_PERIOD_MISMATCH
    assert metrics["price_to_sales"].value is None
