"""Offline presentation regression checks; no Streamlit server or source requests."""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from meli_intelligence.ui import data, domain_storytelling
from meli_intelligence.ui.catalog import get_dataset_catalog
from meli_intelligence.ui.pages import (
    commerce,
    data_quality_sources,
    executive_overview,
    financial,
    fintech,
    macro,
    market,
    pestel,
    product_evidence,
    swot,
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
        return "\n".join(
            str(arg)
            for _, args, _, _ in self.calls
            for arg in args
            if isinstance(arg, str)
        )


@pytest.fixture
def ui():
    global active_ui
    active_ui = RecordingUI()
    return active_ui


def _health(dataset_id, status="AVAILABLE"):
    return SimpleNamespace(
        dataset_id=dataset_id,
        status=status,
        path="synthetic",
        row_count=None,
        column_count=None,
        latest_reference_date=None,
        message="Synthetic dataset health.",
    )


@pytest.mark.parametrize(
    "status,reason",
    [
        ("MISSING", "No local dataset"),
        ("EMPTY", "readable but contains no observations"),
        ("INVALID", "could not be read or validated"),
        ("UNAVAILABLE", "No eligible data"),
        ("UNRECOGNIZED", "reason was not reported"),
    ],
)
def test_shared_unavailable_message_preserves_state_reason_and_boundary(status, reason):
    message = unavailable_message(
        "Example dataset", status, boundary="No values are fabricated."
    )
    assert f"Example dataset: {status}" in message
    assert reason in message
    assert "No values are fabricated." in message
    assert "Data Quality & Sources" in message


def test_shared_message_keeps_supplied_reason_verbatim():
    reason = "Authoritative input is ineligible for the selected date. " * 12
    assert reason in unavailable_message(
        "Example", "UNAVAILABLE", reason=reason, boundary="No estimate is made."
    )


@pytest.mark.parametrize(
    "page",
    [
        commerce,
        fintech,
        financial,
        macro,
        market,
        product_evidence,
        pestel,
        swot,
        executive_overview,
        data_quality_sources,
    ],
)
def test_all_pages_keep_missing_state_visible_without_loading_or_fabricating(
    ui, monkeypatch, page
):
    def unexpected_load(*args, **kwargs):
        pytest.fail("Missing datasets must not be loaded.")

    monkeypatch.setattr(data, "load_dataset", unexpected_load)
    catalog = get_dataset_catalog()
    page.render(ui, [_health(spec.dataset_id, "MISSING") for spec in catalog], catalog)
    assert (
        "indisponível" in ui.text.lower()
        or "missing" in ui.text.lower()
        or "not yet available" in ui.text.lower()
    )
    assert not any(name in {"metric", "line_chart"} for name, _, _, _ in ui.calls)


def test_overview_separates_domain_macro_and_market_reference_dates(ui):
    catalog = get_dataset_catalog()
    records = [_health(spec.dataset_id, "MISSING") for spec in catalog]
    reference_dates = {
        "financial_facts": date(2026, 6, 30),
        "operational_kpis": date(2026, 6, 30),
        "macro_indicators": date(2026, 6, 29),
        "market_prices": date(2026, 7, 2),
        "market_capitalization": date(2026, 7, 1),
    }
    for record in records:
        record.latest_reference_date = reference_dates.get(record.dataset_id)

    executive_overview.render(ui, records, catalog)

    assert "Financeiro**  \n30/06/2026" in ui.text
    assert "Comércio**  \n30/06/2026" in ui.text
    assert "Serviços financeiros**  \n30/06/2026" in ui.text
    assert "Indicadores macroeconômicos**  \n29/06/2026" in ui.text
    assert "Atualização de mercado**  \n02/07/2026" in ui.text
    assert "O que os dados mostram" in ui.text
    assert "Comparações anuais" in ui.text
    assert "Conjuntos disponíveis" not in ui.text
    assert "PESTEL" not in ui.text and "SWOT" not in ui.text
    assert "Discovery" not in ui.text


@pytest.mark.parametrize("status", ["MISSING", "EMPTY", "INVALID"])
def test_product_missing_states_preserve_uncertainty_without_synthesis(
    ui, monkeypatch, status
):
    monkeypatch.setattr(
        product_evidence,
        "select_product_hypotheses",
        lambda *a, **k: pytest.fail(
            "Unavailable Product Evidence must not create hypotheses."
        ),
    )
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
        row.update(
            product_evidence_id=kind,
            product_evidence_type=kind,
            reference_date=date(2024, 3, 31),
            period_type="QUARTER",
            period_start=None,
            period_end=None,
            business_domain="Ecosystem",
            statement=f"Synthetic persisted {kind} text.",
            source="Synthetic evidence",
            rationale="Synthetic stored rationale.",
        )
        for column in row:
            if column.startswith("source_") and column.endswith("ids"):
                row[column] = "[]"
        rows.append(row)
    frame = pd.DataFrame(rows)
    before = frame.copy(deep=True)
    monkeypatch.setattr(data, "load_dataset", lambda *a, **k: frame)
    product_evidence.render(ui, [_health("product_evidence")])
    for statement in frame.statement:
        assert any(
            name == "write" and args == (statement,) for name, args, _, _ in ui.calls
        )
    assert any(
        "not validated Product problems" in str(args) and not nested
        for _, args, _, nested in ui.calls
    )
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("status", ["MISSING", "EMPTY", "INVALID"])
def test_market_states_do_not_imply_product_behavior(ui, monkeypatch, status):
    monkeypatch.setattr(market, "render_valuation", lambda *a, **k: None)
    market.render(ui, [_health("market_prices", status)])
    assert f"MELI market-price data: {status}" in ui.text
    assert "No price is substituted or synthesized." in ui.text
    assert any(
        args == ("Market observations do not establish Product or user behavior.",)
        and not nested
        for _, args, _, nested in ui.calls
    )
    assert not any(name in {"metric", "line_chart"} for name, _, _, _ in ui.calls)


@pytest.mark.parametrize(
    "domain,metric,label",
    [
        ("Commerce", "gmv", "Volume bruto de mercadorias (GMV)"),
        ("Fintech", "tpv", "Volume total de pagamentos (TPV)"),
    ],
)
def test_domain_chart_titles_name_existing_measure_and_preserve_points(
    ui, monkeypatch, domain, metric, label
):
    frame = pd.DataFrame(
        [
            dict(
                metric_id=metric,
                value=value,
                unit="million_usd",
                reference_date=ref,
                period_type="QUARTER",
                period_label="Reported period",
                source="Synthetic source",
            )
            for ref, value in [(date(2024, 3, 31), 100), (date(2024, 9, 30), 90)]
        ]
    )
    monkeypatch.setattr(data, "load_dataset", lambda *a, **k: frame)
    expected = domain_storytelling.select_domain_trend(
        {"operational_kpis": frame}, domain
    )
    domain_storytelling.render_domain_page(ui, [_health("operational_kpis")], domain)
    assert any(
        name == "subheader" and args == (label,) for name, args, _, _ in ui.calls
    )
    chart = next(args[0] for name, args, _, _ in ui.calls if name == "vega_lite_chart")
    pd.testing.assert_series_equal(
        chart["reference_date"], expected["reference_date"], check_names=False
    )
    pd.testing.assert_series_equal(chart["value"], expected["value"], check_names=False)
    assert chart["period_label"].tolist() == ["1º tri. 2024", "3º tri. 2024"]
    assert chart["chart_value"].tolist() == ["US$ 100 mi", "US$ 90 mi"]
    assert "O que os dados mostram" in ui.text
    assert f"{label} atingiu US$ 90 mi em 3º tri. 2024." in ui.text
    assert "Comparação anual" in ui.text
    assert "Não há dados suficientes" in ui.text
    assert "**Limitações**" in ui.text
    assert "não demonstram usuários em comum nem causalidade" in ui.text


def test_financial_page_renders_auditable_quarterly_yoy_narrative(ui, monkeypatch):
    frame = pd.DataFrame(
        [
            {
                "metric_id": "net_revenues_financial_income",
                "value": value,
                "unit": "USD",
                "period_start": start,
                "period_end": end,
                "reference_year": int(end[:4]),
                "period_type": "QUARTER",
                "period_label": f"{quarter} tri. {end[:4]}",
                "form": "10-Q",
                "accession_number": f"acc-{end}",
                "source": "SEC EDGAR",
            }
            for value, start, end, quarter in (
                (100, "2024-01-01", "2024-03-31", "1º"),
                (120, "2025-01-01", "2025-03-31", "1º"),
            )
        ]
    )
    monkeypatch.setattr(
        data,
        "load_dataset",
        lambda dataset_id, **kwargs: (
            frame if dataset_id == "financial_facts" else pd.DataFrame()
        ),
    )

    financial.render(ui, [_health("financial_facts")])

    assert "O que os dados mostram" in ui.text
    assert "US$ 120" in ui.text and "1º tri. 2025" in ui.text
    assert "20,00% em relação ao mesmo trimestre do ano anterior" in ui.text
    assert "Limitações" in ui.text
    assert "interpretações:" not in ui.text
    assert "Disponibilidade de dados financeiros limitada" not in ui.text


def test_macro_chart_title_is_factual_even_when_no_series_is_available(ui):
    macro.render(ui, [])
    assert any(
        name == "subheader"
        and args == ("Meta da taxa Selic · observações diárias reportadas",)
        for name, args, _, _ in ui.calls
    )
    assert not any(name == "line_chart" for name, _, _, _ in ui.calls)
