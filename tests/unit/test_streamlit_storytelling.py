from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.health import DatasetHealth, summarize_health
from meli_intelligence.ui.presentation import (
    MAX_EXECUTIVE_SIGNALS,
    degraded_state_message,
    executive_summary,
    format_compact_number,
    format_date,
    format_metric,
    format_status,
    format_unit,
    latest_global_reference_date,
    product_evidence_counts,
    select_executive_signals,
    select_latest_interpretations,
)
from meli_intelligence.ui.pages.executive_overview import availability_by_domain_layer
from meli_intelligence.ui.storytelling import (
    CENTRAL_QUESTION,
    EXECUTIVE_CONTEXT,
    STORY_FLOW,
    availability_frame,
    build_coverage_summary,
)


def _health(dataset_id: str, status: str, latest: date | None = None) -> DatasetHealth:
    return DatasetHealth(dataset_id, status, f"/{dataset_id}.parquet", 1, 3, latest, "test state")


def _facts() -> dict[str, pd.DataFrame]:
    return {
        "financial_facts": pd.DataFrame([{
            "metric_id": "net_revenues_financial_income", "value": 123456789,
            "unit": "USD", "reference_date": date(2025, 12, 31), "period_type": "QUARTER",
            "source": "SEC Company Facts", "period_label": "Q4 2025",
        }]),
        "operational_kpis": pd.DataFrame([
            {"metric_id": "gmv", "value": 900, "unit": "USD", "reference_date": date(2025, 12, 31), "source": "Release"},
            {"metric_id": "fintech_mau", "value": 80, "unit": "users", "reference_date": date(2025, 12, 31), "source": "Release"},
        ]),
        "macro_indicators": pd.DataFrame([{
            "metric_id": "selic_target_annual", "value": 15, "unit": "percent",
            "reference_date": date(2025, 12, 31), "source": "BCB",
        }]),
    }


def test_signal_selection_is_deterministic_limited_and_domain_aware() -> None:
    frames = _facts()
    original = frames["operational_kpis"].copy(deep=True)
    selected = select_executive_signals(frames)
    assert len(selected) == MAX_EXECUTIVE_SIGNALS == 4
    assert [item.business_domain for item in selected] == ["Financial", "Commerce", "Fintech", "Macro"]
    assert select_executive_signals(frames) == selected
    assert select_executive_signals(frames, max_signals=2) == selected[:2]
    assert select_executive_signals(frames, filters=FilterState(business_domain="Macro"))[0].metric_id == "selic_target_annual"
    assert select_executive_signals(
        frames, filters=FilterState(start_date=date(2026, 1, 1))
    ) == ()
    pd.testing.assert_frame_equal(frames["operational_kpis"], original)


def test_missing_values_are_not_replaced_with_zero() -> None:
    frames = {"macro_indicators": pd.DataFrame([{
        "metric_id": "selic_target_annual", "value": float("nan"),
        "unit": "percent", "reference_date": date(2025, 12, 31),
    }])}
    assert select_executive_signals(frames) == ()
    assert format_metric(float("nan"), "BRL") == "Unavailable"
    assert format_metric(float("inf"), "percent") == "Unavailable"


def test_metric_unit_and_date_formatters_are_consistent() -> None:
    assert format_metric(12.5, "percent") == "12,50%"
    assert format_metric(12.5, "percentage_points") == "12,50 p.p."
    assert format_metric(1200, "BRL", compact=False) == "R$ 1.200,00"
    assert format_compact_number(1_250_000) == "1,25 mi"
    assert format_unit("brl_per_usd") == "R$ per US$"
    assert format_date(date(2025, 12, 31)) == "31 Dec 2025"
    assert format_date(None) == "Unavailable"
    assert format_status("MISSING").startswith("Missing")


def test_executive_signal_formats_currency_millions_and_counts_without_backend_units() -> None:
    financial = pd.DataFrame([{
        "metric_id": "net_revenues_financial_income", "value": 5100,
        "unit": "million_usd", "reference_date": date(2025, 12, 31),
        "period_type": "QUARTER", "source": "Financial source",
    }])
    signal = select_executive_signals({"financial_facts": financial})[0]
    assert signal.formatted_value == "US$ 5.100 mi"
    assert format_metric(12_500, "million_usd") == "US$ 12.500 mi"
    assert "million usd" not in signal.formatted_value.casefold()
    assert signal.unit == "US$ million"
    assert signal.value == 5100.0
    assert "5100" in signal.full_precision_value

    count_frame = pd.DataFrame([{
        "metric_id": "unique_active_buyers", "value": 56_000_000,
        "unit": "count", "reference_date": date(2025, 12, 31), "source": "Operational source",
    }])
    count_signal = select_executive_signals(
        {"operational_kpis": count_frame},
        filters=FilterState(business_domain="Commerce"),
    )[0]
    assert count_signal.formatted_value == "56 mi"
    assert "count" not in count_signal.formatted_value.casefold()
    assert count_signal.value == 56_000_000.0
    assert count_signal.full_precision_value.startswith("56000000")
    assert "count" not in count_signal.full_precision_value.casefold()


def test_large_count_compaction_and_existing_percent_missing_formatting() -> None:
    assert format_metric(61_000_000, "count") == "61 mi"
    assert format_metric(12.5, "percent") == "12,50%"
    assert format_metric(None, "million_usd") == "Unavailable"
    assert "million usd" not in format_metric(None, "million_usd").casefold()


def test_health_summary_degraded_state_and_latest_date() -> None:
    health = (
        _health("a", "AVAILABLE", date(2025, 12, 31)),
        _health("b", "MISSING"),
        _health("c", "EMPTY"),
        _health("d", "INVALID"),
    )
    result = executive_summary(health)
    assert (result.available_count, result.dataset_count) == (1, 4)
    assert result.degraded
    assert latest_global_reference_date(health) == date(2025, 12, 31)
    assert "not yet available" in degraded_state_message(health)
    summary = summarize_health(health)
    assert summary["available_count"] == 1
    assert summary["missing_count"] == summary["empty_count"] == summary["invalid_count"] == 1
    coverage = build_coverage_summary(health, "limited")
    assert coverage.degraded and coverage.message == "limited"
    assert latest_global_reference_date(()) is None


def test_story_copy_and_availability_order_are_explicit() -> None:
    assert STORY_FLOW == ("Context", "Status", "Evidence", "Interpretation", "Next exploration")
    assert "MercadoLibre" in CENTRAL_QUESTION
    assert "does not recommend decisions" in EXECUTIVE_CONTEXT
    catalog = (
        type("Spec", (), {"dataset_id": "z", "business_domains": ("Macro",), "layer": "Silver"})(),
        type("Spec", (), {"dataset_id": "a", "business_domains": ("Financial",), "layer": "Gold"})(),
    )
    records = (_health("z", "MISSING"), _health("a", "AVAILABLE"))
    result = availability_frame(records, catalog)
    assert list(result.business_domain) == ["Financial", "Macro"]


def test_legacy_availability_helper_preserves_contract_and_delegates() -> None:
    catalog = (
        type("Spec", (), {"dataset_id": "a", "business_domains": ("Financial",), "layer": "Gold"})(),
        type("Spec", (), {"dataset_id": "z", "business_domains": ("Macro",), "layer": "Silver"})(),
    )
    records = (_health("a", "AVAILABLE"), _health("z", "MISSING"))
    legacy = availability_by_domain_layer(records, catalog)
    current = availability_frame(records, catalog)
    normalized_legacy = (
        legacy.assign(status=legacy.status.map(format_status))
        .rename(columns={"datasets": "dataset_count"})
        .loc[:, current.columns]
    )
    pd.testing.assert_frame_equal(normalized_legacy, current)
    assert list(legacy.columns) == ["business_domain", "layer", "status", "datasets"]
    assert list(availability_by_domain_layer((), catalog).columns) == [
        "business_domain", "layer", "datasets", "available",
    ]


def test_interpretations_are_capped_and_only_existing_interpretations_are_selected() -> None:
    frame = pd.DataFrame([
        {"evidence_id": f"i{i}", "evidence_type": "INTERPRETATION", "claim": f"Existing claim {i}",
         "source_metric_id": "gmv_yoy_growth", "source": "Existing Evidence", "reference_date": date(2025, 1, i)}
        for i in range(1, 5)
    ] + [{"evidence_id": "obs", "evidence_type": "OBSERVATION", "claim": "fact", "reference_date": date(2025, 1, 31)}])
    selected = select_latest_interpretations(frame)
    assert len(selected) == 3
    assert all(item.metric_id == "gmv_yoy_growth" and item.source and item.reference_date for item in selected)
    assert select_latest_interpretations(pd.DataFrame()) == ()


def test_product_evidence_is_counted_as_discovery_not_recommendation() -> None:
    frame = pd.DataFrame({"product_evidence_type": ["HYPOTHESIS", "QUESTION_FOR_PRODUCT_DISCOVERY"]})
    assert product_evidence_counts(frame) == {"hypotheses": 1, "questions": 1}
    assert product_evidence_counts(None) == {"hypotheses": 0, "questions": 0}


def test_signal_selection_has_no_sign_based_business_judgment() -> None:
    frames = {"macro_indicators": pd.DataFrame([{
        "metric_id": "selic_target_annual", "value": -1.5, "unit": "percent",
        "reference_date": date(2025, 12, 31), "source": "BCB",
    }])}
    selected = select_executive_signals(frames)
    assert len(selected) == 1
    assert selected[0].value == -1.5
    assert "good" not in selected[0].context.lower()
    assert "bad" not in selected[0].context.lower()
    assert not any(word in selected[0].context.lower() for word in ("causes", "proves", "recommend", "should build"))


def test_empty_and_missing_inputs_degrade_without_synthetic_values() -> None:
    assert select_executive_signals({}) == ()
    assert select_latest_interpretations(None) == ()
    message = degraded_state_message((_health("missing", "MISSING"),))
    assert message and "Data availability is limited" in message


def test_page_architecture_remains_thin_read_only_and_minimal() -> None:
    root = Path(__file__).resolve().parents[2]
    pages = root / "src" / "meli_intelligence" / "ui" / "pages"
    page_sources = "\n".join(path.read_text(encoding="utf-8") for path in sorted(pages.glob("*.py")))
    app_source = (root / "streamlit_app.py").read_text(encoding="utf-8")
    presentation_source = (root / "src" / "meli_intelligence" / "ui" / "presentation.py").read_text(encoding="utf-8")
    production_sources = app_source + page_sources + presentation_source
    forbidden_imports = (".sources", ".pipelines", "analytics.macro", "strategy.pestel", "strategy.swot", "product.evidence")
    assert not any(value in production_sources for value in forbidden_imports)
    assert not any(token in page_sources for token in ("to_parquet(", ".to_csv(", "write_parquet(", "DELETE FROM", "INSERT INTO"))
    assert not any(token in page_sources.lower() for token in ("pie_chart(", "donut", "gauge", "radar_chart("))
    normalized = production_sources.casefold()
    assert "existing interpretations" in normalized
    assert 'st.markdown(f"**interpretation · {item.metric_id}**")' in normalized
    assert 'st.markdown(f"**fact · {item.metric_id}**")' not in normalized
    assert 'selected.evidence_type.astype(str) == "interpretation"' in presentation_source.casefold()
    assert "discovery hypotheses" in normalized and "available data" in normalized
    assert "discovery questions" in normalized
    assert "Freshness" in production_sources or "freshness" in production_sources
    assert "No values are substituted or set to zero" in production_sources
    assert "Data availability is limited" in production_sources
    assert "Reference date" in production_sources
    assert "Reset filters" in app_source
    assert "filters.validate()" in app_source
    assert MAX_EXECUTIVE_SIGNALS <= 4


def test_only_supported_filter_state_is_reused() -> None:
    state = FilterState(business_domain="Macro", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    assert state.validate() is state
    with pytest.raises(ValueError, match="on or before"):
        FilterState(start_date=date(2025, 12, 31), end_date=date(2025, 1, 1)).validate()
