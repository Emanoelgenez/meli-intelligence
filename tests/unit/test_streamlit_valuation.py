"""Offline render contracts with synthetic persisted inputs and a recording UI."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import ast

import pandas as pd
import pytest

from meli_intelligence.ui import valuation_storytelling as view
from meli_intelligence.ui.filters import FilterState


class RecordingUI:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return record

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def text(self):
        return "\n".join(str(arg) for _, args, _ in self.calls for arg in args)


@pytest.fixture
def gold():
    return pd.DataFrame([{
        "ticker": "MELI", "reference_date": date(2026, 10, 5),
        "value": 94326976262.25198, "currency": "USD", "status": "AVAILABLE",
        "reason": None, "price": 1860.60999, "shares_outstanding": 50696802,
        "shares_reference_date": date(2026, 8, 5), "shares_filed_at": date(2026, 8, 6),
        "shares_accession_number": "0001099590-26-000023",
        "source_metric_ids": "market:close;dei:EntityCommonStockSharesOutstanding",
        "methodology_version": "1", "market_source": "Synthetic Market source",
        "market_source_url": "https://example.invalid/market",
    }])


@pytest.fixture
def facts():
    return pd.DataFrame([{
        "metric_id": metric, "value": 10000000000, "unit": "USD",
        "period_start": None if metric == "stockholders_equity" else date(2026, 4, 1),
        "period_end": date(2026, 6, 30),
        "period_type": "INSTANT" if metric == "stockholders_equity" else "QUARTER",
        "filed_at": date(2026, 8, 6), "accession_number": "synthetic-equity-filing",
    } for metric in ("stockholders_equity", "net_revenues_financial_income", "operating_cash_flow")])


def render(monkeypatch, gold, facts, **kwargs):
    from meli_intelligence.ui import data
    frames = {"market_capitalization": gold, "financial_facts": facts}
    def load(dataset_id, **options):
        assert "filters" not in options  # Do not prune historical financial denominators.
        value = frames[dataset_id]
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(data, "load_dataset", load)
    records = [SimpleNamespace(dataset_id=key, status="MISSING" if value is None else "AVAILABLE", path="synthetic")
               for key, value in frames.items()]
    ui = RecordingUI()
    view.render(ui, records, **kwargs)
    return ui


def test_backend_consumption_and_exact_persisted_date(monkeypatch, gold, facts):
    calls = []
    original = view.build_valuation_snapshot
    def spy(g, f, **kwargs):
        calls.append((g, f, kwargs))
        return original(g, f, **kwargs)
    monkeypatch.setattr(view, "build_valuation_snapshot", spy)
    before = gold.copy(deep=True)
    snapshot = view.valuation_view(gold, facts)
    assert calls[0][0] is gold and calls[0][1] is facts
    assert snapshot.valuation_reference_date == date(2026, 10, 5)
    assert snapshot.market_cap.value == gold.iloc[0].value
    pd.testing.assert_frame_equal(gold, before)


def test_available_render_formats_values_and_lineage(monkeypatch, gold, facts):
    ui = render(monkeypatch, gold, facts)
    metrics = [args for name, args, _ in ui.calls if name == "metric"]
    assert metrics == [("Market capitalization", "US$ 94,33 bi"), ("Price to book", "9.43x")]
    assert "05 Oct 2026" in ui.text
    for value in ("05 Aug 2026", "06 Aug 2026", "0001099590-26-000023", "synthetic-equity-filing", "Synthetic Market source", "Methodology version: 1"):
        assert value in ui.text
    assert "trailing-twelve-month" in ui.text
    assert "Price to sales: Unavailable" in ui.text
    assert "Price to operating cash flow: Unavailable" in ui.text
    assert not any("earnings" in args[0].lower() or "P/E" in args[0] for args in metrics)
    assert any(name == "expander" for name, _, _ in ui.calls)


@pytest.mark.parametrize("value,reason", [(0, "not finite and positive"), (-1, "not finite and positive")])
def test_invalid_book_value_has_explicit_reason(monkeypatch, gold, facts, value, reason):
    facts.loc[facts.metric_id == "stockholders_equity", "value"] = value
    ui = render(monkeypatch, gold, facts)
    assert "Price to book: Unavailable" in ui.text and reason in ui.text
    assert len([1 for name, _, _ in ui.calls if name == "metric"]) == 1


def test_future_filed_equity_is_unavailable(monkeypatch, gold, facts):
    facts["filed_at"] = date(2026, 10, 6)
    assert "filing date is after" in render(monkeypatch, gold, facts).text


def test_latest_unavailable_does_not_fall_back(monkeypatch, gold, facts):
    latest = gold.copy()
    latest["reference_date"] = date(2026, 10, 6)
    latest["status"] = "UNAVAILABLE_MISSING_SHARE_COUNT"
    latest["reason"] = "Authoritative shares unavailable."
    latest["value"] = None
    ui = render(monkeypatch, pd.concat([gold, latest]), facts)
    assert "06 Oct 2026" in ui.text
    assert "UNAVAILABLE_GOLD_MARKET_CAP" in ui.text
    assert "UNAVAILABLE_MISSING_SHARE_COUNT" in ui.text
    assert "Authoritative shares unavailable." in ui.text
    assert not any(name == "metric" for name, _, _ in ui.calls)


@pytest.mark.parametrize("missing", ["gold", "facts", "both"])
def test_absent_files_render_safely(monkeypatch, gold, facts, missing):
    ui = render(monkeypatch, FileNotFoundError() if missing in ("gold", "both") else gold,
                FileNotFoundError() if missing in ("facts", "both") else facts)
    assert "MISSING" in ui.text and "Unavailable" in ui.text
    assert "Data Quality & Sources" in ui.text
    assert not any(name == "metric" and args[0] == "Price to book" for name, args, _ in ui.calls)


@pytest.mark.parametrize("frame", [None, pd.DataFrame(), pd.DataFrame({"bad": [1]})])
def test_missing_empty_invalid_frames(monkeypatch, frame, facts):
    ui = render(monkeypatch, frame, facts)
    assert not any(name == "metric" for name, _, _ in ui.calls)
    assert "Unavailable" in ui.text or "INVALID" in ui.text


def test_date_range_bounds_gold_but_not_financial_history(gold, facts):
    assert view.valuation_view(gold, facts, filters=FilterState(end_date=date(2026, 10, 4))) is None
    snapshot = view.valuation_view(gold, facts, filters=FilterState(start_date=date(2026, 10, 5)))
    assert next(m for m in snapshot.metrics if m.metric_id == "price_to_book").status == "AVAILABLE"
    with pytest.raises(ValueError):
        view.valuation_view(gold, facts, filters=FilterState(start_date=date(2026, 10, 6), end_date=date(2026, 10, 5)))


@pytest.mark.parametrize("column,value", [("ticker", "MELI34"), ("currency", "BRL")])
def test_meli_usd_scope(monkeypatch, gold, facts, column, value):
    gold[column] = value
    ui = render(monkeypatch, gold, facts)
    assert not any(name == "metric" for name, _, _ in ui.calls)


def test_catalog_routes_gold_to_validating_reader(monkeypatch, tmp_path):
    from meli_intelligence.storage import market_cap
    from meli_intelligence.ui.catalog import get_dataset_spec
    from meli_intelligence.ui.data import load_dataset
    path = tmp_path / "synthetic.parquet"
    path.touch()
    expected = pd.DataFrame({"value": [1.]})
    calls = []
    def read(path):
        calls.append(path)
        return expected
    monkeypatch.setattr(market_cap, "read_market_cap_gold", read)
    spec = get_dataset_spec("market_capitalization")
    assert spec.optional and spec.layer == "Gold"
    pd.testing.assert_frame_equal(load_dataset(spec.dataset_id, path=path), expected)
    assert calls == [path]


def test_ui_architecture_has_no_analytics_network_or_product_inference():
    source = Path(view.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(any(word in (module or "") for word in ("product", "sources", "pipelines", "httpx")) for module in imports)
    assert not any(isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)) for node in ast.walk(tree))
    for token in ("calculate_market_cap", "select_financial_fact_as_of", "to_parquet", "read_csv", "requests", "delta_color", "target price", "fair value", "gauge"):
        assert token not in source.lower()
    words = set(source.lower().split())
    assert not words.intersection({"red", "green", "buy", "sell", "hold"})
    assert "streamlit" not in imports


def test_market_page_keeps_price_section_and_embeds_valuation(monkeypatch):
    from meli_intelligence.ui.pages import market
    calls = []
    monkeypatch.setattr(market, "render_valuation", lambda *args, **kwargs: calls.append(kwargs))
    ui = RecordingUI()
    market.render(ui, [])
    assert calls and "Market dataset status: MISSING" in ui.text
    assert ("title", ("Market",), {}) in ui.calls


@pytest.mark.parametrize("mode", ["missing", "empty", "invalid", "filtered", "available"])
def test_valuation_scope_is_visible_before_every_return(monkeypatch, gold, facts, mode):
    frames = {"missing": None, "empty": pd.DataFrame(), "invalid": pd.DataFrame({"bad": [1]}),
              "filtered": gold, "available": gold}
    filters = FilterState(end_date=date(2026, 10, 4)) if mode == "filtered" else None
    ui = render(monkeypatch, frames[mode], facts, filters=filters)
    scope = next(index for index, (name, args, _) in enumerate(ui.calls)
                 if name == "caption" and "P/E is outside the current scope" in args[0])
    assert "quarterly facts are not annualized" in ui.calls[scope][1][0]
    assert not any(name == "expander" for name, _, _ in ui.calls[:scope])
    assert not any(name == "columns" for name, _, _ in ui.calls)


def test_no_snapshot_keeps_long_ratio_explanations_separate(monkeypatch, facts):
    ui = render(monkeypatch, None, facts)
    info = [args[0] for name, args, _ in ui.calls if name == "info"]
    reason = "eligible market capitalization and valid TTM denominators are required."
    assert f"Price to sales: Unavailable — {reason}" in info
    assert f"Price to operating cash flow: Unavailable — {reason}" in info
    assert not any(name == "metric" for name, _, _ in ui.calls)


def test_backend_unavailable_reasons_remain_verbatim_full_width(monkeypatch, gold, facts):
    snapshot = view.valuation_view(gold, facts)
    ui = render(monkeypatch, gold, facts)
    info = [args[0] for name, args, _ in ui.calls if name == "info"]
    for metric in snapshot.metrics:
        if metric.status != "AVAILABLE":
            assert f"{metric.label}: Unavailable — {metric.reason}" in info
    assert not any(name == "columns" for name, _, _ in ui.calls)
