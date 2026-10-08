from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.ui.domain_storytelling import (
    COMMERCE_METRICS,
    DOMAIN_METRICS,
    FINTECH_METRICS,
    domain_freshness,
    domain_metric_label,
    domain_metric_availability,
    domain_navigation_order,
    select_domain_interpretations,
    select_domain_snapshots,
    select_domain_trend,
)
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.pages.executive_overview import availability_by_domain_layer


def _operational(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "unit": "USD",
        "period_type": "QUARTER",
        "period_label": "Q1 2025",
        "source": "SEC reported release",
        "filing_date": date(2025, 5, 1),
        "accession_number": "0001",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows])


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "operational_kpis": _operational([
            {"metric_id": "gmv", "value": 100_000_000, "period_end": date(2024, 12, 31), "period_label": "Q4 2024"},
            {"metric_id": "gmv", "value": 125_000_000, "period_end": date(2025, 3, 31), "period_label": "Q1 2025"},
            {"metric_id": "unique_active_buyers", "value": 50_000_000, "period_end": date(2024, 12, 31), "unit": "users", "period_label": "Q4 2024"},
            {"metric_id": "fintech_mau", "value": 60_000_000, "period_end": date(2025, 3, 31), "unit": "users", "period_label": "Q1 2025"},
            {"metric_id": "tpv", "value": 12_500_000_000, "period_end": date(2025, 3, 31), "period_label": "Q1 2025"},
            {"metric_id": "some_unlisted_metric", "value": 999, "period_end": date(2025, 3, 31)},
        ]),
        "extended_operational_kpis": pd.DataFrame([
            {"metric_id": "aum", "value": 20_000_000_000, "unit": "USD", "period_end": date(2024, 12, 31), "period_type": "INSTANT", "period_label": "Q4 2024", "source": "SEC reported release", "filing_date": date(2025, 2, 1), "accession_number": "0002"},
            {"metric_id": "credit_portfolio", "value": 15_000_000_000, "unit": "USD", "period_end": date(2025, 3, 31), "period_type": "INSTANT", "period_label": "Q1 2025", "source": "SEC reported release", "filing_date": date(2025, 5, 1), "accession_number": "0003"},
            {"metric_id": "npl_15_90_total", "value": 7.1, "unit": "percent", "period_end": date(2025, 3, 31), "period_type": "INSTANT", "period_label": "Q1 2025", "source": "SEC reported release", "filing_date": date(2025, 5, 1), "accession_number": "0004"},
        ]),
    }


def test_allowlists_use_real_published_metric_ids_and_are_deterministic() -> None:
    assert tuple(item.metric_id for item in COMMERCE_METRICS) == (
        "gmv", "unique_active_buyers", "items_sold",
    )
    assert tuple(item.metric_id for item in FINTECH_METRICS) == (
        "fintech_mau", "tpv", "aum", "credit_portfolio", "npl_15_90_total",
    )
    assert DOMAIN_METRICS == {"Commerce": COMMERCE_METRICS, "Fintech": FINTECH_METRICS}
    assert tuple(item.metric_id for item in COMMERCE_METRICS) == tuple(item.metric_id for item in DOMAIN_METRICS["Commerce"])


@pytest.mark.parametrize("domain", ["Commerce", "Fintech"])
def test_domain_snapshots_are_prioritized_limited_and_preserve_period_source(domain: str) -> None:
    frames = _frames()
    snapshots = select_domain_snapshots(frames, domain)
    assert len(snapshots) <= 4
    assert all(item.business_domain == domain for item in snapshots)
    assert all(item.reference_date and item.period_label and item.source for item in snapshots)
    if domain == "Commerce":
        assert [item.metric_id for item in snapshots] == ["gmv", "unique_active_buyers"]
        assert snapshots[0].reference_date == date(2025, 3, 31)
    else:
        assert [item.metric_id for item in snapshots] == ["fintech_mau", "tpv", "aum", "credit_portfolio"]
        assert snapshots[2].reference_date == date(2024, 12, 31)
        assert "npl_15_90_total" not in [item.metric_id for item in snapshots]


def test_snapshots_do_not_mutate_input_and_missing_metrics_never_become_zero() -> None:
    frames = _frames()
    before = {key: value.copy(deep=True) for key, value in frames.items()}
    snapshots = select_domain_snapshots(frames, "Commerce")
    assert "items_sold" not in [item.metric_id for item in snapshots]
    assert all(item.value != 0 for item in snapshots)
    assert frames["operational_kpis"].equals(before["operational_kpis"])
    assert frames["extended_operational_kpis"].equals(before["extended_operational_kpis"])
    assert select_domain_snapshots(None, "Commerce") == ()
    assert select_domain_snapshots({"operational_kpis": pd.DataFrame()}, "Fintech") == ()
    assert "Items sold" in domain_metric_availability(frames, "Commerce")


def test_metric_labels_hide_backend_ids_in_existing_interpretations() -> None:
    assert domain_metric_label("gmv", "Commerce") == "Gross merchandise volume (GMV)"
    assert domain_metric_label("tpv_yoy_growth", "Fintech") == "Payment volume year-over-year growth"
    assert "tpv_yoy_growth" not in domain_metric_label("tpv_yoy_growth", "Fintech")


def test_domain_pages_ignore_global_domain_filter_but_respect_dates() -> None:
    frames = _frames()
    state = FilterState(business_domain="Fintech", start_date=date(2025, 1, 1), end_date=date(2025, 3, 31))
    commerce = select_domain_snapshots(frames, "Commerce", filters=state)
    assert [item.metric_id for item in commerce] == ["gmv"]
    assert domain_freshness(frames, "Commerce", filters=state) == date(2025, 3, 31)
    with pytest.raises(ValueError, match="on or before"):
        select_domain_snapshots(frames, "Commerce", filters=FilterState(start_date=date(2025, 4, 1), end_date=date(2025, 3, 31)))


def test_trend_is_chronological_raw_and_does_not_fill_missing_periods() -> None:
    frame = _operational([
        {"metric_id": "gmv", "value": 30, "period_end": date(2025, 3, 31), "period_label": "Q1 2025"},
        {"metric_id": "gmv", "value": 10, "period_end": date(2024, 3, 31), "period_label": "Q1 2024"},
    ])
    before = frame.copy(deep=True)
    result = select_domain_trend({"operational_kpis": frame}, "Commerce")
    assert result.reference_date.tolist() == [date(2024, 3, 31), date(2025, 3, 31)]
    assert result.value.tolist() == [10, 30]
    assert len(result) == 2
    assert frame.equals(before)
    assert select_domain_trend(
        {"operational_kpis": frame}, "Commerce",
        filters=FilterState(start_date=date(2024, 4, 1), end_date=date(2024, 12, 31)),
    ).empty
    with pytest.raises(ValueError, match="not allowlisted"):
        select_domain_trend({"operational_kpis": frame}, "Commerce", metric_id="fintech_mau")


def test_interpretations_are_domain_scoped_limited_and_only_existing_interpretations() -> None:
    frame = pd.DataFrame([
        {"evidence_id": f"i-{i}", "evidence_type": typ, "business_domain": domain,
         "source_metric_id": metric, "metric_id": metric, "claim": "Existing text.",
         "source": "Source", "reference_date": date(2025, 3, i)}
        for i, (typ, domain, metric) in enumerate([
            ("INTERPRETATION", "Commerce", "gmv"),
            ("OBSERVATION", "Commerce", "gmv"),
            ("INTERPRETATION", "Fintech", "tpv"),
            ("INTERPRETATION", "Commerce", "unique_active_buyers"),
            ("INTERPRETATION", "Commerce", "items_sold"),
            ("INTERPRETATION", "Commerce", "gmv"),
        ], start=1)
    ])
    selected = select_domain_interpretations(frame, "Commerce")
    assert len(selected) == 3
    assert set(selected.evidence_type) == {"INTERPRETATION"}
    assert set(selected.business_domain) == {"Commerce"}
    assert select_domain_interpretations(None, "Commerce").empty


def test_domain_page_architecture_remains_read_only_thin_and_navigation_compatible() -> None:
    root = Path(__file__).resolve().parents[2]
    ui = root / "src" / "meli_intelligence" / "ui"
    pages = ui / "pages"
    page_sources = "\n".join(path.read_text(encoding="utf-8") for path in (pages / "commerce.py", pages / "fintech.py"))
    app_source = (root / "streamlit_app.py").read_text(encoding="utf-8")
    assert domain_navigation_order() == (
        "Executive Overview", "Financial", "Commerce", "Fintech", "Macro", "PESTEL", "SWOT",
        "Product Evidence", "Market", "Data Quality & Sources",
    )
    from meli_intelligence.ui.pages import NAVIGATION_OPTIONS
    assert NAVIGATION_OPTIONS == domain_navigation_order()
    # The old 5A helper remains part of the public page-module contract.
    assert callable(availability_by_domain_layer)
    assert not any(token in page_sources for token in (".sources", ".pipelines", "to_parquet(", ".to_csv(", "write_parquet("))
    assert not any(token in page_sources.lower() for token in ("pie_chart(", "donut", "gauge", "radar_chart("))
    domain_source = (ui / "domain_storytelling.py").read_text(encoding="utf-8")
    assert "render_domain_page" in page_sources
    assert "select_domain_snapshots" in domain_source
    assert all(token in app_source for token in ("commerce.render", "fintech.render"))
    assert "MELI Intelligence" in app_source


def test_cross_domain_caveat_rejects_overlap_causality_and_recommendation_copy() -> None:
    source = (Path(__file__).resolve().parents[2] / "src" / "meli_intelligence" / "ui" / "domain_storytelling.py").read_text(encoding="utf-8").casefold()
    for concept in ("user overlap", "cross-domain retention", "causality", "product recommendations"):
        assert concept in source
    assert "ecosystem-user count" in source
    assert "engagement score" not in source
