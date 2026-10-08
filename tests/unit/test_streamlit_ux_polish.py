"""Offline presentation regression checks; no Streamlit server or source requests."""
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from meli_intelligence.ui import data, domain_storytelling
from meli_intelligence.ui.catalog import get_dataset_catalog
from meli_intelligence.ui.pages import (
    commerce, data_quality_sources, executive_overview, financial, fintech,
    macro, market, pestel, product_evidence, swot,
)
from meli_intelligence.ui.presentation import unavailable_message


class RecordingUI:
    def __init__(self, calls=None, expanders=()):
        self.calls = [] if calls is None else calls
        self.expanders = expanders

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs, self.expanders))
            if name == "columns":
                return [RecordingUI(self.calls, self.expanders) for _ in range(args[0])]
            if name == "expander":
                return RecordingUI(self.calls, self.expanders + (args[0],))
            if name == "checkbox":
                return False
            return self
        return record

    def __enter__(self):
        # Pages call st inside context managers, so record nesting on the root too.
        self._previous = active_ui.expanders
        active_ui.expanders = self.expanders
        return self

    def __exit__(self, *args):
        active_ui.expanders = self._previous
        return False

    @property
    def text(self):
        return "\n".join(str(arg) for _, args, _, _ in self.calls for arg in args if isinstance(arg, str))


@pytest.fixture
def ui():
    global active_ui
    active_ui = RecordingUI()
    return active_ui


def _health(dataset_id, status="AVAILABLE"):
    return SimpleNamespace(dataset_id=dataset_id, status=status, path="synthetic",
                           row_count=None, column_count=None,
                           latest_reference_date=None, message="Synthetic dataset health.")


@pytest.mark.parametrize("status,reason", [
    ("MISSING", "No local dataset"),
    ("EMPTY", "readable but contains no observations"),
    ("INVALID", "could not be read or validated"),
    ("UNAVAILABLE", "No eligible data"),
    ("UNRECOGNIZED", "reason was not reported"),
])
def test_shared_unavailable_message_preserves_state_reason_and_boundary(status, reason):
    message = unavailable_message("Example dataset", status, boundary="No values are fabricated.")
    assert f"Example dataset: {status}" in message
    assert reason in message
    assert "No values are fabricated." in message
    assert "Data Quality & Sources" in message


def test_shared_message_keeps_supplied_reason_verbatim():
    reason = "Authoritative input is ineligible for the selected date. " * 12
    assert reason in unavailable_message("Example", "UNAVAILABLE", reason=reason, boundary="No estimate is made.")


@pytest.mark.parametrize("page", [commerce, fintech, financial, macro, market, product_evidence,
                                   pestel, swot, executive_overview, data_quality_sources])
def test_all_pages_keep_missing_state_visible_without_loading_or_fabricating(ui, monkeypatch, page):
    def unexpected_load(*args, **kwargs):
        pytest.fail("Missing datasets must not be loaded.")
    monkeypatch.setattr(data, "load_dataset", unexpected_load)
    catalog = get_dataset_catalog()
    page.render(ui, [_health(spec.dataset_id, "MISSING") for spec in catalog], catalog)
    assert "missing" in ui.text.lower() or "not yet available" in ui.text.lower()
    assert not any(name in {"metric", "line_chart"} for name, _, _, _ in ui.calls)


@pytest.mark.parametrize("status", ["MISSING", "EMPTY", "INVALID"])
def test_product_missing_states_preserve_uncertainty_without_synthesis(ui, monkeypatch, status):
    monkeypatch.setattr(product_evidence, "select_product_hypotheses",
                        lambda *a, **k: pytest.fail("Unavailable Product Evidence must not create hypotheses."))
    product_evidence.render(ui, [_health("product_evidence", status)])
    assert f"Product Evidence data status: {status}" in ui.text
    assert "No hypotheses or questions are fabricated." in ui.text
    assert "not validated Product problems" in ui.text
    assert "do not establish user-level overlap" in ui.text
    assert "Data Quality & Sources" in ui.text
    assert not any(name == "metric" for name, _, _, _ in ui.calls)


def test_product_read_failure_preserves_visible_limits(ui, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("Synthetic read failure")
    monkeypatch.setattr(data, "load_dataset", fail)
    product_evidence.render(ui, [_health("product_evidence")])
    assert "INVALID" in ui.text and "Read diagnostic: ValueError" in ui.text
    assert "not validated Product problems" in ui.text
    assert "No hypotheses or questions are fabricated." in ui.text


def test_product_records_remain_verbatim_and_limits_outside_expanders(ui, monkeypatch):
    from meli_intelligence.product.evidence import PRODUCT_EVIDENCE_COLUMNS
    rows = []
    for kind in ("HYPOTHESIS", "QUESTION_FOR_PRODUCT_DISCOVERY"):
        row = {column: "" for column in PRODUCT_EVIDENCE_COLUMNS}
        row.update(product_evidence_id=kind, product_evidence_type=kind,
                   reference_date=date(2024, 3, 31), period_type="QUARTER",
                   period_start=None, period_end=None, business_domain="Ecosystem",
                   statement=f"Synthetic persisted {kind} text.", source="Synthetic evidence",
                   rationale="Synthetic stored rationale.")
        for column in row:
            if column.startswith("source_") and column.endswith("ids"):
                row[column] = "[]"
        rows.append(row)
    frame = pd.DataFrame(rows)
    before = frame.copy(deep=True)
    monkeypatch.setattr(data, "load_dataset", lambda *a, **k: frame)
    product_evidence.render(ui, [_health("product_evidence")])
    for statement in frame.statement:
        assert any(name == "write" and args == (statement,) for name, args, _, _ in ui.calls)
    assert any("not validated Product problems" in str(args) and not nested
               for _, args, _, nested in ui.calls)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("status", ["MISSING", "EMPTY", "INVALID"])
def test_market_states_do_not_imply_product_behavior(ui, monkeypatch, status):
    monkeypatch.setattr(market, "render_valuation", lambda *a, **k: None)
    market.render(ui, [_health("market_prices", status)])
    assert f"MELI market-price data: {status}" in ui.text
    assert "No price is substituted or synthesized." in ui.text
    assert any(args == ("Market observations do not establish Product or user behavior.",) and not nested
               for _, args, _, nested in ui.calls)
    assert not any(name in {"metric", "line_chart"} for name, _, _, _ in ui.calls)


@pytest.mark.parametrize("domain,metric,label", [
    ("Commerce", "gmv", "Gross merchandise volume (GMV)"),
    ("Fintech", "tpv", "Total payment volume (TPV)"),
])
def test_domain_chart_titles_name_existing_measure_and_preserve_points(ui, monkeypatch, domain, metric, label):
    frame = pd.DataFrame([dict(metric_id=metric, value=value, unit="million_usd",
                               reference_date=ref, period_type="QUARTER", period_label="Reported period",
                               source="Synthetic source")
                          for ref, value in [(date(2024, 3, 31), 100), (date(2024, 9, 30), 90)]])
    monkeypatch.setattr(data, "load_dataset", lambda *a, **k: frame)
    expected = domain_storytelling.select_domain_trend({"operational_kpis": frame}, domain)
    domain_storytelling.render_domain_page(ui, [_health("operational_kpis")], domain)
    assert any(name == "subheader" and args == (f"Reported {label}",) for name, args, _, _ in ui.calls)
    chart = next(args[0] for name, args, _, _ in ui.calls if name == "line_chart")
    pd.testing.assert_frame_equal(chart, expected)
    assert "does not establish user overlap or causality" in ui.text


def test_macro_chart_title_is_factual_even_when_no_series_is_available(ui):
    macro.render(ui, [])
    assert any(name == "subheader" and args == ("Target Selic rate · daily reported observations",)
               for name, args, _, _ in ui.calls)
    assert not any(name == "line_chart" for name, _, _, _ in ui.calls)
