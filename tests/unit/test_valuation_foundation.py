"""Synthetic, data-independent checks for the conservative valuation foundation."""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
import re

import pandas as pd

from meli_intelligence.analytics.valuation import (
    STATUS_MISSING_MARKET_CAP,
    VALUATION_STATUSES,
    build_valuation_availability,
    select_financial_fact_as_of,
)


def _fact(metric_id, *, period_type, start, end, filed, value, accession="a1"):
    return {
        "metric_id": metric_id,
        "value": value,
        "unit": "USD",
        "period_start": start,
        "period_end": end,
        "period_type": period_type,
        "filed_at": filed,
        "accession_number": accession,
        "is_derived": False,
    }


def test_missing_market_cap_makes_all_candidate_multiples_explicitly_unavailable():
    metrics = build_valuation_availability(market_reference_date=date(2026, 10, 5))
    assert [metric.metric_id for metric in metrics] == [
        "price_to_sales", "price_to_book", "price_to_operating_cash_flow",
    ]
    assert all(metric.status == STATUS_MISSING_MARKET_CAP for metric in metrics)
    assert all(metric.value is None for metric in metrics)
    assert all("market capitalization" in metric.reason for metric in metrics)
    assert all(metric.reference_date == date(2026, 10, 5) for metric in metrics)


def test_availability_accepts_only_a_market_cap_contract_not_guessed_shares():
    import inspect

    parameters = inspect.signature(build_valuation_availability).parameters
    assert "shares_outstanding" not in parameters
    assert "market_cap" in parameters
    assert all(metric.metric_id != "market_cap" for metric in build_valuation_availability())


def test_asof_selection_excludes_filings_after_market_reference_date():
    facts = pd.DataFrame([
        _fact("net_revenues_financial_income", period_type="QUARTER", start="2023-10-01", end="2023-12-31",
              filed="2024-02-15", value=100, accession="late"),
        _fact("net_revenues_financial_income", period_type="QUARTER", start="2023-07-01", end="2023-09-30",
              filed="2023-11-01", value=90, accession="available"),
    ])
    selected = select_financial_fact_as_of(
        facts, metric_id="net_revenues_financial_income", market_reference_date=date(2024, 1, 31),
    )
    assert selected is not None
    assert selected.accession_number == "available"
    assert selected.filed_at <= date(2024, 1, 31)
    assert selected.period_end == date(2023, 9, 30)


def test_duration_and_instant_facts_remain_distinct():
    facts = pd.DataFrame([
        _fact("net_revenues_financial_income", period_type="INSTANT", start=None, end="2025-12-31",
              filed="2026-02-01", value=100),
        _fact("stockholders_equity", period_type="QUARTER", start="2025-10-01", end="2025-12-31",
              filed="2026-02-01", value=50),
        _fact("operating_cash_flow", period_type="YTD", start="2025-01-01", end="2025-12-31",
              filed="2026-02-01", value=80),
    ])
    ref = date(2026, 3, 1)
    assert select_financial_fact_as_of(facts, metric_id="net_revenues_financial_income", market_reference_date=ref) is None
    assert select_financial_fact_as_of(facts, metric_id="stockholders_equity", market_reference_date=ref) is None
    assert select_financial_fact_as_of(facts, metric_id="operating_cash_flow", market_reference_date=ref) is None

    compatible = pd.DataFrame([
        _fact("net_revenues_financial_income", period_type="QUARTER", start="2025-10-01", end="2025-12-31",
              filed="2026-02-01", value=100),
        _fact("stockholders_equity", period_type="INSTANT", start=None, end="2025-12-31",
              filed="2026-02-01", value=50),
    ])
    revenue = select_financial_fact_as_of(compatible, metric_id="net_revenues_financial_income", market_reference_date=ref)
    equity = select_financial_fact_as_of(compatible, metric_id="stockholders_equity", market_reference_date=ref)
    assert revenue and revenue.period_type == "QUARTER" and revenue.period_start is not None
    assert equity and equity.period_type == "INSTANT" and equity.period_start is None


def test_status_and_reason_are_deterministic_and_unavailable_is_not_zero():
    first = build_valuation_availability()
    second = build_valuation_availability()
    assert [(m.status, m.reason, m.value) for m in first] == [(m.status, m.reason, m.value) for m in second]
    assert all(m.status in VALUATION_STATUSES for m in first)
    assert all(m.value is None and m.value != 0 for m in first)


def test_no_product_import_or_product_inference_dependency():
    path = Path(__file__).resolve().parents[2] / "src" / "meli_intelligence" / "analytics" / "valuation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("product" in name.lower() for name in imported)


def test_project_owned_streamlit_calls_use_width_api_not_deprecated_parameter():
    root = Path(__file__).resolve().parents[2]
    sources = [*root.joinpath("src").rglob("*.py"), root / "streamlit_app.py"]
    assert not any(re.search(r"use_container_width\s*=", path.read_text(encoding="utf-8")) for path in sources)
    assert "width=\"stretch\"" in "\n".join(path.read_text(encoding="utf-8") for path in sources)
