from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import sys

import pandas as pd
import pytest

from meli_intelligence.product.evidence import PRODUCT_EVIDENCE_COLUMNS
from meli_intelligence.ui.domain_storytelling import domain_navigation_order
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.product_storytelling import (
    DISCOVERY_QUESTION,
    HYPOTHESIS,
    PRODUCT_EVIDENCE_PRESENTATION_COLUMNS,
    product_evidence_freshness,
    product_evidence_summary,
    select_discovery_questions,
    select_product_hypotheses,
    select_supporting_evidence,
)


def _product_row(
    evidence_type: str,
    evidence_id: str,
    reference_date: date,
    *,
    source_evidence_ids: tuple[str, ...] = (),
    source_hypothesis_ids: tuple[str, ...] = (),
) -> dict:
    return {
        "product_evidence_id": evidence_id,
        "product_evidence_type": evidence_type,
        "discovery_theme": "ECOSYSTEM_ENGAGEMENT",
        "business_domain": "Ecosystem",
        "reference_date": reference_date,
        "period_start": date(reference_date.year, 1, 1),
        "period_end": reference_date,
        "period_type": "QUARTER",
        "entity": "MercadoLibre",
        "statement": f"Persisted {evidence_type} statement for {evidence_id}.",
        "rationale": "Persisted rationale with aggregate-data limits.",
        "source_evidence_ids": json.dumps(list(source_evidence_ids)),
        "source_interpretation_ids": "[]",
        "source_pestel_ids": "[]",
        "source_swot_ids": "[]",
        "source_hypothesis_ids": json.dumps(list(source_hypothesis_ids)),
        "source_metric_ids": json.dumps(["gmv_yoy_growth", "fintech_mau_yoy_growth"]),
        "source": "Existing evidence registry",
        "methodology_version": "1",
        "definition_context": "aggregate_metrics_only;no_user_level_overlap_inference",
        "scope": "AGGREGATE",
    }


def _frame() -> pd.DataFrame:
    hypotheses = [
        _product_row(HYPOTHESIS, f"h-{index}", date(2024, index, 28), source_evidence_ids=(f"e-{index}",))
        for index in range(1, 5)
    ]
    questions = [
        _product_row(
            DISCOVERY_QUESTION,
            f"q-{index}",
            date(2024, index, 28),
            source_evidence_ids=(f"e-{index}",),
            source_hypothesis_ids=(f"h-{index}",),
        )
        for index in range(1, 7)
    ]
    return pd.DataFrame(hypotheses + questions, columns=PRODUCT_EVIDENCE_COLUMNS)


def test_real_schema_types_theme_domain_and_lineage_are_used() -> None:
    frame = _frame()
    assert tuple(frame.columns) == tuple(PRODUCT_EVIDENCE_COLUMNS)
    assert tuple(frame.columns) == PRODUCT_EVIDENCE_PRESENTATION_COLUMNS
    assert set(frame.product_evidence_type) == {HYPOTHESIS, DISCOVERY_QUESTION}
    assert set(frame.discovery_theme) == {"ECOSYSTEM_ENGAGEMENT"}
    assert set(frame.business_domain) == {"Ecosystem"}
    assert json.loads(frame.iloc[0].source_evidence_ids) == ["e-1"]
    assert json.loads(frame.iloc[-1].source_hypothesis_ids) == ["h-6"]


def test_only_persisted_hypotheses_and_questions_are_selected() -> None:
    frame = _frame()
    assert set(select_product_hypotheses(frame).product_evidence_type) == {HYPOTHESIS}
    assert set(select_discovery_questions(frame).product_evidence_type) == {DISCOVERY_QUESTION}
    # Source FACT/OBSERVATION/INTERPRETATION records are never accepted as Product types.
    invalid = frame.copy()
    invalid.loc[0, "product_evidence_type"] = "FACT"
    with pytest.raises(ValueError, match="Unsupported Product Evidence types"):
        select_product_hypotheses(invalid)


def test_selection_is_recent_first_stable_and_capped() -> None:
    frame = _frame()
    hypotheses = select_product_hypotheses(frame)
    questions = select_discovery_questions(frame)
    assert len(hypotheses) == 3
    assert len(questions) == 5
    assert hypotheses.product_evidence_id.tolist() == ["h-4", "h-3", "h-2"]
    assert questions.product_evidence_id.tolist() == ["q-6", "q-5", "q-4", "q-3", "q-2"]
    reversed_frame = frame.iloc[::-1].reset_index(drop=True)
    assert select_product_hypotheses(reversed_frame).product_evidence_id.tolist() == hypotheses.product_evidence_id.tolist()
    assert select_discovery_questions(reversed_frame).product_evidence_id.tolist() == questions.product_evidence_id.tolist()


def test_summary_freshness_and_date_filters_use_reference_date_only() -> None:
    frame = _frame()
    before = frame.copy(deep=True)
    summary = product_evidence_summary(frame)
    assert (summary.hypothesis_count, summary.question_count) == (4, 6)
    assert summary.latest_reference_date == date(2024, 6, 28)
    assert product_evidence_freshness(frame) == date(2024, 6, 28)
    state = FilterState(business_domain="Commerce", start_date=date(2024, 3, 1), end_date=date(2024, 4, 30))
    # Product Evidence is cross-domain; the global domain selection is intentionally not applied.
    hypotheses = select_product_hypotheses(frame, filters=state, limit=10)
    questions = select_discovery_questions(frame, filters=state, limit=10)
    assert set(hypotheses.product_evidence_id) == {"h-3", "h-4"}
    assert set(questions.product_evidence_id) == {"q-3", "q-4"}
    assert product_evidence_summary(frame, filters=state).latest_reference_date == date(2024, 4, 28)
    assert frame.equals(before)
    with pytest.raises(ValueError, match="on or before"):
        select_product_hypotheses(frame, filters=FilterState(start_date=date(2024, 4, 1), end_date=date(2024, 3, 1)))


def test_missing_and_empty_inputs_degrade_without_fabricated_counts() -> None:
    missing = product_evidence_summary(None)
    assert not missing.available
    assert missing.hypothesis_count is None and missing.question_count is None
    assert missing.latest_reference_date is None
    empty = pd.DataFrame(columns=PRODUCT_EVIDENCE_COLUMNS)
    summary = product_evidence_summary(empty)
    assert summary.available
    assert (summary.hypothesis_count, summary.question_count) == (0, 0)
    assert summary.latest_reference_date is None
    assert select_product_hypotheses(None).empty
    assert select_discovery_questions(empty).empty


def test_evidence_lineage_is_exact_and_original_types_are_preserved() -> None:
    frame = _frame()
    items = pd.concat([select_product_hypotheses(frame), select_discovery_questions(frame)], ignore_index=True)
    registry = pd.DataFrame([
        {"evidence_id": "e-4", "evidence_type": "FACT", "business_domain": "Commerce", "metric_id": "gmv", "reference_date": date(2024, 1, 28), "claim": "Reported GMV.", "source": "SEC"},
        {"evidence_id": "e-5", "evidence_type": "OBSERVATION", "business_domain": "Fintech", "metric_id": "fintech_mau", "reference_date": date(2024, 2, 28), "claim": "Reported Fintech MAU.", "source": "Company filing"},
        {"evidence_id": "unlinked", "evidence_type": "INTERPRETATION", "business_domain": "Macro", "metric_id": "selic", "reference_date": date(2024, 2, 28), "claim": "Not linked to selected Product Evidence.", "source": "BCB"},
    ])
    selected = select_supporting_evidence(items, registry)
    assert set(selected.evidence_id) == {"e-4", "e-5"}
    assert set(selected.evidence_type) == {"FACT", "OBSERVATION"}
    assert "unlinked" not in set(selected.evidence_id)
    assert select_supporting_evidence(items.iloc[0:0], registry).empty
    without_lineage = items.iloc[[0]].copy()
    without_lineage["source_evidence_ids"] = "[]"
    assert select_supporting_evidence(without_lineage, registry).empty


def test_presentation_preserves_hypothesis_and_question_text_verbatim() -> None:
    frame = _frame()
    hypotheses = select_product_hypotheses(frame)
    questions = select_discovery_questions(frame)
    source_statements = dict(zip(frame.product_evidence_id, frame.statement))
    assert all(source_statements[row.product_evidence_id] == row.statement for _, row in hypotheses.iterrows())
    assert all(source_statements[row.product_evidence_id] == row.statement for _, row in questions.iterrows())
    assert set(hypotheses.business_domain) == {"Ecosystem"}
    assert set(hypotheses.discovery_theme) == {"ECOSYSTEM_ENGAGEMENT"}
    assert all("aggregate_metrics_only" in context for context in hypotheses.definition_context)
    expected_lineage = frame.set_index("product_evidence_id").source_evidence_ids
    assert all(
        expected_lineage[row.product_evidence_id] == row.source_evidence_ids
        for _, row in hypotheses.iterrows()
    )


def test_ui_architecture_is_read_only_thin_and_navigation_compatible() -> None:
    root = Path(__file__).resolve().parents[2]
    page_path = root / "src" / "meli_intelligence" / "ui" / "pages" / "product_evidence.py"
    helper_path = root / "src" / "meli_intelligence" / "ui" / "product_storytelling.py"
    page_source = page_path.read_text(encoding="utf-8").casefold()
    helper_source = helper_path.read_text(encoding="utf-8").casefold()
    app_source = (root / "streamlit_app.py").read_text(encoding="utf-8")
    forbidden_imports = (".sources", ".pipelines", ".transformations")
    assert not any(token in page_source for token in forbidden_imports)
    assert not any(token in page_source for token in ("to_parquet(", ".to_csv(", "write_parquet("))
    assert not any(token in page_source for token in ("line_chart(", "bar_chart(", "pie_chart(", "plotly_chart("))
    assert "import streamlit" not in page_source and "import streamlit" not in helper_source
    assert not any(token in helper_source for token in ("engagement_score", "ecosystem_score", "confidence_score", "overlap_estimate"))
    assert "product_evidence.render" in app_source
    assert "Business-domain filtering is not shown for this cross-domain page." in app_source
    assert domain_navigation_order() == (
        "Executive Overview", "Financial", "Commerce", "Fintech", "Macro", "PESTEL", "SWOT",
        "Product Evidence", "Market", "Data Quality & Sources",
    )
    assert "source_evidence_ids" in page_source and "definition context" in page_source
    assert not re.search(r"\b(users?\s+(?:want|need)|should build|we recommend)\b", page_source)
    import streamlit_app
    assert callable(streamlit_app.main)
    assert "streamlit" not in sys.modules


def test_prior_ui_contracts_remain_importable() -> None:
    from meli_intelligence.ui.pages.executive_overview import availability_by_domain_layer
    from meli_intelligence.ui.domain_storytelling import (
        domain_navigation_order as prior_domain_navigation_order,
        select_domain_snapshots,
    )
    from meli_intelligence.ui.macro_storytelling import select_macro_snapshots
    from meli_intelligence.ui.strategy_storytelling import summarize_pestel, summarize_swot

    assert callable(availability_by_domain_layer)
    assert callable(select_domain_snapshots)
    assert callable(select_macro_snapshots)
    assert callable(summarize_pestel) and callable(summarize_swot)
    assert prior_domain_navigation_order()[-3] == "Product Evidence"
