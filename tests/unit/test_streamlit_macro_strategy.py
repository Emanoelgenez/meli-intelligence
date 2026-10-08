from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.ui.macro_storytelling import (
    MACRO_ADDITIONAL,
    MACRO_PRIORITY,
    MACRO_TREND_METRICS,
    format_macro_value,
    macro_freshness,
    select_macro_observations,
    select_macro_snapshots,
    select_macro_trend,
)
from meli_intelligence.ui.strategy_storytelling import (
    PESTEL_ORDER,
    SWOT_ORDER,
    select_pestel_items,
    select_swot_items,
    summarize_pestel,
    summarize_swot,
)
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.pages.executive_overview import availability_by_domain_layer
from meli_intelligence.ui.domain_storytelling import domain_navigation_order


def _macro_fact(metric: str, ref: date, value: float, unit: str, frequency: str, **extra) -> dict:
    return {
        "metric_id": metric,
        "reference_date": ref,
        "value": value,
        "unit": unit,
        "frequency": frequency,
        "source": "BCB",
        "source_url": "https://bcb.example/source",
        **extra,
    }


def _macro_frames() -> dict[str, pd.DataFrame]:
    return {
        "macro_indicators": pd.DataFrame([
            _macro_fact("selic_target_annual", date(2024, 3, 20), 11.25, "percent_per_year", "daily"),
            _macro_fact("selic_target_annual", date(2024, 3, 21), 11.25, "percent_per_year", "daily"),
            _macro_fact("selic_target_annual", date(2024, 6, 30), 10.5, "percent_per_year", "daily"),
            _macro_fact("ipca_12m_change", date(2024, 5, 31), 3.9, "percent", "monthly"),
            _macro_fact("usd_brl_sell_rate", date(2024, 5, 31), 5.2, "brl_per_usd", "daily"),
            _macro_fact("unemployment_rate_rolling_3m", date(2024, 4, 30), 7.5, "percent", "rolling_3m_monthly"),
            _macro_fact("pix_transactions_count_monthly", date(2024, 5, 31), 2_000_000_000, "transactions", "monthly"),
            _macro_fact("future_metric_not_allowlisted", date(2024, 6, 30), 99, "count", "monthly"),
        ]),
        "macro_analytics": pd.DataFrame([
            {"metric_id": "selic_target_change_pp", "reference_date": date(2024, 6, 30), "value": -0.75,
             "unit": "percentage_points", "frequency": "daily", "source": "BCB", "source_metric_id": "selic_target_annual",
             "analytics_kind": "previous_observation_change", "definition_context": "existing"},
            {"metric_id": "usd_brl_month_end", "reference_date": date(2024, 5, 31), "value": 5.2,
             "unit": "brl_per_usd", "frequency": "monthly", "source": "BCB", "source_metric_id": "usd_brl_sell_rate",
             "analytics_kind": "month_end_snapshot", "definition_context": "existing"},
        ]),
    }


def _pestel_row(pid: str, dimension: str, metric: str, ref: date, **extra) -> dict:
    return {
        "pestel_id": pid,
        "pestel_dimension": dimension,
        "business_domain": "Macro",
        "reference_date": ref,
        "claim": f"Persisted claim for {metric}.",
        "classification_rationale": "Classification rationale from the PESTEL registry.",
        "source_evidence_ids": json.dumps([f"e-{pid}"]),
        "source_evidence_types": json.dumps(["OBSERVATION"]),
        "source_metric_ids": json.dumps([metric]),
        "source": "Official source",
        "is_interpretation": False,
        "definition_context": "Persisted definition.",
        **extra,
    }


def _swot_row(sid: str, category: str, scope: str, domain: str, ref: date, metric: str, **extra) -> dict:
    return {
        "swot_id": sid,
        "swot_category": category,
        "business_domain": domain,
        "reference_date": ref,
        "claim": f"Persisted claim {sid}.",
        "assessment": f"Persisted assessment {sid}.",
        "classification_rationale": "Persisted allowlist rationale.",
        "source_evidence_ids": json.dumps([f"e-{sid}"]),
        "source_evidence_types": json.dumps(["OBSERVATION"]),
        "source_metric_ids": json.dumps([metric]),
        "source_pestel_ids": json.dumps([f"p-{sid}"]) if scope == "EXTERNAL" else "[]",
        "source_pestel_dimensions": json.dumps(["ECONOMIC"]) if scope == "EXTERNAL" else "[]",
        "source": "Persisted source",
        "scope": scope,
        "is_interpretation": True,
        "definition_context": "Persisted context.",
        "value": 100 if category in {"STRENGTH", "OPPORTUNITY"} else -100,
        **extra,
    }


def test_macro_allowlists_are_real_fixed_and_prioritized() -> None:
    assert tuple(spec.metric_id for spec in MACRO_PRIORITY) == (
        "selic_target_annual", "ipca_12m_change", "usd_brl_sell_rate", "unemployment_rate_rolling_3m",
    )
    known = {spec.metric_id for spec in MACRO_PRIORITY + MACRO_ADDITIONAL}
    assert {"ibc_br_activity_sa_index", "retail_sales_volume_mom_sa", "pix_transactions_count_monthly"}.issubset(known)
    assert {"selic_effective_annual_252", "ipca_monthly_change", "ipca_12m_change_pp"}.issubset(known)
    assert MACRO_TREND_METRICS == {"selic_target_annual"}
    assert tuple(spec.metric_id for spec in MACRO_PRIORITY) == tuple(spec.metric_id for spec in MACRO_PRIORITY)


def test_macro_snapshots_cap_cards_keep_each_date_and_ignore_future_registry_ids() -> None:
    frames = _macro_frames()
    snapshots = select_macro_snapshots(frames, metric_ids=tuple(spec.metric_id for spec in MACRO_PRIORITY))
    assert len(snapshots) <= 4
    assert [item.metric_id for item in snapshots] == [spec.metric_id for spec in MACRO_PRIORITY]
    assert snapshots[0].reference_date == date(2024, 6, 30)
    assert snapshots[1].reference_date == date(2024, 5, 31)
    assert snapshots[0].frequency == "daily" and snapshots[1].frequency == "monthly"
    assert all(item.source == "BCB" and item.full_precision_value for item in snapshots)
    with pytest.raises(ValueError, match="non-allowlisted"):
        select_macro_snapshots(frames, metric_ids=("future_metric_not_allowlisted",))
    with pytest.raises(ValueError, match="between 0 and"):
        select_macro_snapshots(frames, limit=30)


def test_macro_missing_is_not_zero_and_units_and_labels_are_friendly() -> None:
    snapshots = select_macro_snapshots({"macro_indicators": pd.DataFrame([
        _macro_fact("selic_target_annual", date(2024, 1, 31), 11.25, "percent_per_year", "daily"),
    ])})
    assert len(snapshots) == 1
    assert snapshots[0].formatted_value == "11,25% a.a."
    assert snapshots[0].display_name == "Target Selic rate"
    assert snapshots[0].value == 11.25
    assert "selic_target_annual" not in snapshots[0].display_name
    assert format_macro_value(2_000_000_000, "transactions") == "2 bi transactions"
    assert format_macro_value(5.2345, "brl_per_usd").startswith("R$ 5,2345")
    assert format_macro_value(None, "percent") == "Unavailable"
    assert select_macro_snapshots(None) == ()
    assert select_macro_snapshots({"macro_indicators": pd.DataFrame()}) == ()


def test_macro_trend_is_chronological_original_frequency_and_does_not_fill_gaps() -> None:
    frames = _macro_frames()
    before = frames["macro_indicators"].copy(deep=True)
    trend = select_macro_trend(frames)
    assert trend.reference_date.tolist() == [date(2024, 3, 20), date(2024, 3, 21), date(2024, 6, 30)]
    assert trend.value.tolist() == [11.25, 11.25, 10.5]
    assert len(trend) == 3
    assert frames["macro_indicators"].equals(before)
    with pytest.raises(ValueError, match="not allowlisted"):
        select_macro_trend(frames, metric_id="ipca_12m_change")


def test_macro_filters_and_freshness_use_reference_dates() -> None:
    frames = _macro_frames()
    state = FilterState(start_date=date(2024, 4, 1), end_date=date(2024, 5, 31))
    latest = select_macro_snapshots(frames, filters=state, metric_ids=("selic_target_annual",), limit=1)
    assert latest == ()
    assert macro_freshness(frames, filters=state) == date(2024, 5, 31)
    with pytest.raises(ValueError, match="on or before"):
        select_macro_snapshots(frames, filters=FilterState(start_date=date(2024, 6, 1), end_date=date(2024, 5, 1)))


def test_macro_existing_observations_only_and_limit() -> None:
    frame = pd.DataFrame([
        {"evidence_id": "obs-1", "evidence_type": "OBSERVATION", "business_domain": "Macro", "metric_id": "ipca_12m_change", "reference_date": date(2024, 1, 31), "claim": "Existing observation.", "source": "BCB", "source_metric_id": "ipca_12m_change"},
        {"evidence_id": "fact-1", "evidence_type": "FACT", "business_domain": "Macro", "metric_id": "ipca_12m_change", "reference_date": date(2024, 2, 29), "claim": "Fact.", "source": "BCB", "source_metric_id": "ipca_12m_change"},
        {"evidence_id": "other-1", "evidence_type": "OBSERVATION", "business_domain": "Commerce", "metric_id": "gmv", "reference_date": date(2024, 2, 29), "claim": "Other domain.", "source": "SEC", "source_metric_id": "gmv"},
    ])
    result = select_macro_observations(frame)
    assert result.evidence_id.tolist() == ["obs-1"]
    assert select_macro_observations(None).empty
    with pytest.raises(ValueError, match="limit"):
        select_macro_observations(frame, limit=4)


def test_pestel_order_coverage_absent_dimensions_and_persisted_lineage() -> None:
    frame = pd.DataFrame([
        _pestel_row("p2", "SOCIAL", "fintech_mau_yoy_growth", date(2024, 4, 30)),
        _pestel_row("p1", "ECONOMIC", "selic_target_change_pp", date(2024, 5, 31)),
    ])
    summary = summarize_pestel(frame)
    assert summary.record_count == 2
    assert summary.covered_dimensions == ("ECONOMIC", "SOCIAL")
    assert summary.absent_dimensions == tuple(d for d in PESTEL_ORDER if d not in {"ECONOMIC", "SOCIAL"})
    assert dict(summary.dimension_counts)["POLITICAL"] == 0
    selected = select_pestel_items(frame, limit=2)
    assert selected.pestel_id.tolist() == ["p1", "p2"]
    assert selected.iloc[0].source_evidence_ids == frame.loc[frame.pestel_id == "p1", "source_evidence_ids"].iloc[0]
    assert PESTEL_ORDER == ("POLITICAL", "ECONOMIC", "SOCIAL", "TECHNOLOGICAL", "ENVIRONMENTAL", "LEGAL")
    assert summarize_pestel(None).record_count is None
    assert summarize_pestel(pd.DataFrame(columns=frame.columns)).record_count == 0


def test_pestel_date_filter_order_and_invalid_dimension() -> None:
    frame = pd.DataFrame([
        _pestel_row("old", "ECONOMIC", "ipca_12m_change", date(2023, 1, 31)),
        _pestel_row("new", "ECONOMIC", "ipca_12m_change", date(2024, 1, 31)),
        _pestel_row("social", "SOCIAL", "fintech_mau_yoy_growth", date(2024, 1, 31)),
    ])
    before = frame.copy(deep=True)
    filtered = select_pestel_items(frame, filters=FilterState(start_date=date(2024, 1, 1)), limit=2)
    assert filtered.pestel_id.tolist() == ["new", "social"]
    assert frame.equals(before)
    invalid = frame.copy()
    invalid.loc[0, "pestel_dimension"] = "SWOT"
    with pytest.raises(ValueError, match="unsupported dimensions"):
        summarize_pestel(invalid)
    with pytest.raises(ValueError, match="on or before"):
        select_pestel_items(frame, filters=FilterState(start_date=date(2024, 2, 1), end_date=date(2024, 1, 1)))


def test_swot_summary_order_scope_and_no_reclassification_by_value() -> None:
    frame = pd.DataFrame([
        _swot_row("s1", "STRENGTH", "INTERNAL", "Commerce", date(2024, 3, 31), "gmv_yoy_growth"),
        _swot_row("w1", "WEAKNESS", "INTERNAL", "Fintech", date(2024, 3, 31), "tpv_yoy_growth"),
        _swot_row("o1", "OPPORTUNITY", "EXTERNAL", "Macro", date(2024, 3, 31), "pix_transactions_count_yoy_growth"),
        _swot_row("t1", "THREAT", "EXTERNAL", "Macro", date(2024, 3, 31), "selic_target_change_pp"),
    ])
    summary = summarize_swot(frame)
    assert summary.record_count == 4
    assert summary.category_counts == tuple((category, 1) for category in SWOT_ORDER)
    assert (summary.internal_count, summary.external_count) == (2, 2)
    assert SWOT_ORDER == ("STRENGTH", "WEAKNESS", "OPPORTUNITY", "THREAT")
    # The helper returns stored classification; numeric value does not create or alter a category.
    selected = select_swot_items(frame, category="THREAT", scope="EXTERNAL")
    assert selected.swot_id.tolist() == ["t1"]
    assert selected.iloc[0].swot_category == "THREAT"
    assert selected.iloc[0].source_evidence_ids == frame.loc[frame.swot_id == "t1", "source_evidence_ids"].iloc[0]
    assert summarize_swot(None).record_count is None
    assert summarize_swot(pd.DataFrame(columns=frame.columns)).record_count == 0


def test_swot_filters_categories_and_scopes_without_inventing_coverage() -> None:
    frame = pd.DataFrame([
        _swot_row("ext", "OPPORTUNITY", "EXTERNAL", "Macro", date(2024, 1, 31), "pix_transactions_count_yoy_growth"),
        _swot_row("int", "STRENGTH", "INTERNAL", "Commerce", date(2024, 2, 29), "gmv_yoy_growth"),
    ])
    filtered = select_swot_items(frame, scope="EXTERNAL", filters=FilterState(end_date=date(2024, 1, 31)))
    assert filtered.swot_id.tolist() == ["ext"]
    assert len(select_swot_items(frame, category="WEAKNESS")) == 0
    counts = dict(summarize_swot(frame).category_counts)
    assert counts["WEAKNESS"] == counts["THREAT"] == 0
    with pytest.raises(ValueError, match="Invalid SWOT category"):
        select_swot_items(frame, category="POLITICAL")
    with pytest.raises(ValueError, match="Invalid SWOT scope"):
        select_swot_items(frame, scope="MACRO")
    with pytest.raises(ValueError, match="on or before"):
        select_swot_items(frame, filters=FilterState(start_date=date(2024, 3, 1), end_date=date(2024, 2, 1)))


def test_pages_preserve_layer_contracts_navigation_and_architecture() -> None:
    root = Path(__file__).resolve().parents[2]
    pages = root / "src" / "meli_intelligence" / "ui" / "pages"
    page_sources = "\n".join(
        (pages / name).read_text(encoding="utf-8")
        for name in ("macro.py", "pestel.py", "swot.py")
    )
    helper_sources = "\n".join(
        (root / "src" / "meli_intelligence" / "ui" / name).read_text(encoding="utf-8")
        for name in ("macro_storytelling.py", "strategy_storytelling.py")
    )
    app_source = (root / "streamlit_app.py").read_text(encoding="utf-8")
    from meli_intelligence.ui.pages import NAVIGATION_OPTIONS
    assert NAVIGATION_OPTIONS == (
        "Executive Overview", "Financial", "Commerce", "Fintech", "Macro", "PESTEL", "SWOT",
        "Product Evidence", "Market", "Data Quality & Sources"
    )
    assert domain_navigation_order() == NAVIGATION_OPTIONS
    assert callable(availability_by_domain_layer)
    assert all(f"{name}.render" in app_source for name in ("macro", "pestel", "swot"))
    assert not any(token in page_sources for token in ("meli_intelligence.sources", "meli_intelligence.pipelines", "meli_intelligence.transformations"))
    assert not any(token in page_sources.lower() for token in ("to_parquet(", ".to_csv(", "write_parquet(", "pie_chart(", "donut", "gauge", "radar_chart("))
    assert "dual_axis" not in page_sources.casefold() and "secondary_y=True" not in page_sources.casefold()
    assert "build_macro_analytics" not in helper_sources and "build_pestel(" not in helper_sources and "build_swot(" not in helper_sources
    assert "interpolate(" not in helper_sources and ".resample(" not in helper_sources
    assert "reference_date" in page_sources and "Latest applicable reference date" in page_sources
    assert "source_evidence_ids" in page_sources and "interpretation" in page_sources.casefold()
