import json
from datetime import date

import pandas as pd
import pyarrow.parquet as pq
import pytest

from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence
from meli_intelligence.query.swot import query_swot
from meli_intelligence.storage.swot import write_swot
from meli_intelligence.strategy.pestel import build_pestel
from meli_intelligence.strategy.swot import (
    SWOT_CATEGORIES,
    SWOT_COLUMNS,
    build_swot,
    validate_swot,
    validate_swot_lineage,
)


def evidence(
    *, eid="internal-1", metric="fintech_mau_yoy_growth", domain="Fintech",
    value=12.0, kind="yoy_growth", typ="OBSERVATION", claim="Fintech MAU increased 12% YoY.",
    context="definition_version=v1", ref=date(2024, 3, 31), source_ids="[]",
):
    return {
        "evidence_id": eid, "evidence_type": typ, "business_domain": domain,
        "entity": "MercadoLibre" if domain != "Macro" else "Brazil", "metric_id": metric,
        "reference_date": ref, "period_start": None, "period_end": ref,
        "period_type": "MONTH", "period_label": ref.strftime("%Y-%m"), "value": value,
        "unit": "percent", "frequency": "monthly", "claim": claim, "claim_kind": kind,
        "source": "official source", "source_url": None, "filing_date": None,
        "accession_number": None, "source_bronze_file": None, "source_content_sha256": None,
        "source_metric_id": metric, "source_evidence_ids": source_ids,
        "is_interpretation": typ == "INTERPRETATION", "methodology_version": "1",
        "definition_context": context,
    }


def registry(*rows):
    return normalize_evidence(pd.DataFrame(rows, columns=EVIDENCE_COLUMNS))


def pix_registry():
    return registry(evidence(
        eid="pix-growth", metric="pix_transactions_count_yoy_growth", domain="Macro",
        value=25, kind="technology_adoption", claim="Pix transaction count increased 25% YoY.",
        context="technology_adoption;explicit_digital_infrastructure",
    ))


def pestel_for(reg):
    return build_pestel(reg)


def test_strength_for_allowlisted_internal_metric():
    result = build_swot(registry(evidence()))
    assert result.swot_category.tolist() == ["STRENGTH"]
    assert result.scope.tolist() == ["INTERNAL"]


def test_weakness_for_allowlisted_negative_internal_growth():
    result = build_swot(registry(evidence(value=-4, kind="yoy_decline", claim="Fintech MAU declined 4% YoY.")))
    assert result.swot_category.tolist() == ["WEAKNESS"]


def test_no_sign_only_or_unlisted_internal_classification():
    unlisted = evidence(eid="unlisted-positive", metric="some_other_positive_metric", value=99, kind="increase")
    wrong_domain = evidence(eid="wrong-domain-mau", metric="fintech_mau_yoy_growth", domain="Commerce", value=12)
    assert build_swot(registry(unlisted, wrong_domain)).empty


@pytest.mark.parametrize("metric", ["household_free_credit_npl_90d_rate", "household_free_credit_npl_90d_yoy_change_pp"])
def test_bcb_npl_is_not_internal_meli_weakness(metric):
    source = evidence(eid="bcb-npl", metric=metric, domain="Macro", value=8, kind="increase", claim="BCB household NPL above 90 days was reported.")
    assert build_swot(registry(source)).empty


def test_macro_never_becomes_strength_or_weakness():
    rows = [
        evidence(eid="macro-pos", metric="selic_target_change_pp", domain="Macro", value=1, kind="increase"),
        evidence(eid="macro-neg", metric="selic_target_change_pp", domain="Macro", value=-1, kind="decrease"),
    ]
    # Selic's external rules require matching PESTEL and can only produce THREAT.
    reg = registry(*rows)
    result = build_swot(reg, pestel_for(reg))
    assert not set(result.swot_category) & {"STRENGTH", "WEAKNESS"}


def test_internal_never_becomes_external_category():
    reg = registry(evidence())
    result = build_swot(reg, pestel_for(reg))
    assert not set(result.swot_category) & {"OPPORTUNITY", "THREAT"}
    assert json.loads(result.iloc[0].source_pestel_ids) == []


def test_pix_opportunity_requires_technological_pestel_lineage():
    reg = pix_registry()
    pestel = pestel_for(reg)
    result = build_swot(reg, pestel)
    assert result.swot_category.tolist() == ["OPPORTUNITY"]
    assert json.loads(result.iloc[0].source_pestel_ids) == pestel.pestel_id.tolist()
    assert json.loads(result.iloc[0].source_pestel_dimensions) == ["TECHNOLOGICAL"]


def test_pix_candidate_without_pestel_is_rejected():
    with pytest.raises(ValueError, match="requires compatible PESTEL lineage"):
        build_swot(pix_registry())


def test_rising_selic_threat_requires_economic_pestel():
    reg = registry(evidence(
        eid="selic-rise", metric="selic_target_change_pp", domain="Macro", value=0.5,
        kind="increase", claim="Selic target increased by 0.5 percentage points.",
    ))
    out = build_swot(reg, pestel_for(reg))
    assert out.swot_category.tolist() == ["THREAT"]
    assert out.source_pestel_dimensions.map(lambda value: json.loads(value)).tolist() == [["ECONOMIC"]]


def test_no_forced_coverage_for_unsupported_external_rules():
    reg = registry(evidence(eid="macro-other", metric="ipca_12m_change_pp", domain="Macro", value=0.5, kind="acceleration"))
    assert build_swot(reg, pestel_for(reg)).empty


def test_evidence_and_pestel_lineage_are_required_and_compatible():
    reg = pix_registry()
    pestel = pestel_for(reg)
    out = build_swot(reg, pestel)
    bad_evidence = out.copy()
    bad_evidence.loc[0, "source_evidence_ids"] = '["unknown"]'
    with pytest.raises(ValueError, match="Unknown source_evidence_id"):
        validate_swot_lineage(bad_evidence, reg, pestel)
    bad_pestel = out.copy()
    bad_pestel.loc[0, "source_pestel_ids"] = '["unknown-pestel"]'
    with pytest.raises(ValueError, match="Unknown source_pestel_id"):
        validate_swot_lineage(bad_pestel, reg, pestel)
    no_pestel = out.copy()
    no_pestel.loc[0, "source_pestel_ids"] = "[]"
    no_pestel.loc[0, "source_pestel_dimensions"] = "[]"
    with pytest.raises(ValueError, match="External SWOT requires"):
        validate_swot_lineage(no_pestel, reg, pestel)


def test_evidence_pestel_metric_mismatch_fails():
    reg = pix_registry()
    pestel = pestel_for(reg)
    pestel.loc[0, "source_metric_ids"] = '["unrelated_metric"]'
    with pytest.raises(ValueError, match="Evidence/PESTEL metric lineage is incompatible"):
        build_swot(reg, pestel)


def test_internal_and_external_scope_cannot_be_mixed_in_lineage():
    internal = evidence(eid="internal", metric="fintech_mau_yoy_growth", domain="Fintech")
    external = evidence(eid="external", metric="macro_fact", domain="Macro", value=1, kind="level")
    interp = evidence(eid="mixed-interp", metric="fintech_mau_yoy_growth", domain="Fintech", typ="INTERPRETATION", source_ids='["internal","external"]')
    reg = registry(internal, external, interp)
    with pytest.raises(ValueError, match="incompatible|Internal SWOT"):
        build_swot(reg)


def test_temporal_incompatibility_blocks_lineage():
    first = evidence(eid="source-a", metric="raw_metric_a", value=1, kind="level", ref=date(2024, 3, 31))
    second = evidence(eid="source-b", metric="raw_metric_b", value=2, kind="level", ref=date(2023, 12, 31))
    derived = evidence(eid="derived", metric="fintech_mau_yoy_growth", typ="INTERPRETATION", source_ids='["source-a","source-b"]')
    with pytest.raises(ValueError, match="periods are incompatible"):
        build_swot(registry(first, second, derived))


def test_definition_incompatibility_blocks_lineage():
    first = evidence(eid="source-a", metric="raw_metric_a", value=1, kind="level", context="definition_version=v1")
    second = evidence(eid="source-b", metric="raw_metric_b", value=2, kind="level", context="definition_version=v2")
    derived = evidence(eid="derived", metric="fintech_mau_yoy_growth", typ="INTERPRETATION", source_ids='["source-a","source-b"]')
    with pytest.raises(ValueError, match="definitions are incompatible"):
        build_swot(registry(first, second, derived))


def test_valid_categories_and_invalid_category():
    assert SWOT_CATEGORIES == {"STRENGTH", "WEAKNESS", "OPPORTUNITY", "THREAT"}
    result = build_swot(registry(evidence()))
    invalid = result.copy()
    invalid.loc[0, "swot_category"] = "PESTEL"
    with pytest.raises(ValueError, match="Invalid SWOT categories"):
        validate_swot(invalid)


def test_claim_preserved_assessment_rationale_and_source_metadata():
    source = evidence(claim="Fintech MAU increased 12% YoY.")
    out = build_swot(registry(source)).iloc[0]
    assert out.claim == source["claim"]
    assert out.assessment and out.classification_rationale
    assert json.loads(out.source_evidence_types) == ["OBSERVATION"]
    assert json.loads(out.source_metric_ids) == ["fintech_mau_yoy_growth"]
    assert bool(out.is_interpretation) is True


def test_deterministic_ids_and_ordering():
    rows = [evidence(eid="b", metric="fintech_mau_yoy_growth"), evidence(eid="a", metric="gmv_yoy_growth", domain="Commerce")]
    a = build_swot(registry(*rows))
    b = build_swot(registry(*reversed(rows)))
    assert a.swot_id.tolist() == b.swot_id.tolist()
    assert a.swot_id.is_unique


def test_language_guard_blocks_causal_prescriptive_and_product_claims():
    prohibited = ["This caused the result.", "We recommend a solution.", "This proves a feature is needed.", "Product opportunity identified.", "Deveria construir uma solução."]
    for claim in prohibited:
        with pytest.raises(ValueError, match="causal or prescriptive"):
            build_swot(registry(evidence(claim=claim)))


def test_swot_category_opportunity_is_not_itself_language_guarded():
    result = build_swot(pix_registry(), pestel_for(pix_registry()))
    assert result.iloc[0].swot_category == "OPPORTUNITY"


def test_query_validates_category_before_filesystem(tmp_path):
    missing = tmp_path / "missing.parquet"
    with pytest.raises(ValueError, match="Invalid SWOT category"):
        query_swot(path=missing, swot_category="PESTEL")
    with pytest.raises(FileNotFoundError):
        query_swot(path=missing, swot_category="STRENGTH")


def test_storage_query_replay_conflict_and_zstd(tmp_path):
    reg = registry(evidence())
    out = build_swot(reg)
    path = tmp_path / "swot.parquet"
    write_swot(out, path)
    write_swot(out, path)
    assert pq.read_metadata(path).row_group(0).column(0).compression == "ZSTD"
    assert len(query_swot(path=path, swot_category="STRENGTH")) == 1
    assert len(query_swot(path=path, business_domain="Fintech")) == 1
    assert len(query_swot(path=path, metric_id="fintech_mau_yoy_growth")) == 1
    assert len(query_swot(path=path, source_evidence_id="internal-1")) == 1
    assert len(query_swot(path=path, start_date=date(2024, 3, 1), end_date=date(2024, 3, 31))) == 1
    assert query_swot(path=path, end_date=date(2024, 2, 29)).empty
    conflict = out.copy()
    conflict.loc[0, "assessment"] = "A different classification assessment."
    with pytest.raises(ValueError, match="identity conflict"):
        write_swot(conflict, path)


def test_query_can_filter_pestel_lineage(tmp_path):
    reg = pix_registry()
    pestel = pestel_for(reg)
    result = build_swot(reg, pestel)
    path = tmp_path / "swot.parquet"
    write_swot(result, path)
    pestel_id = result.iloc[0].source_pestel_ids
    assert len(query_swot(path=path, source_pestel_id=json.loads(pestel_id)[0])) == 1


def test_swot_schema_contains_required_audit_fields():
    result = build_swot(registry(evidence()))
    assert list(result.columns) == SWOT_COLUMNS
    assert {"swot_id", "claim", "assessment", "source_evidence_ids", "source_pestel_ids", "definition_context"}.issubset(SWOT_COLUMNS)

def test_internal_swot_rejects_pestel_lineage():
    out = build_swot(registry(evidence()))
    out.loc[0, "source_pestel_ids"] = '["pestel-1"]'
    out.loc[0, "source_pestel_dimensions"] = '["SOCIAL"]'
    with pytest.raises(ValueError, match="Internal SWOT requires"):
        validate_swot(out)


def test_bcb_and_meli_npl_definition_mix_is_rejected():
    bcb = evidence(eid="bcb", metric="household_free_credit_npl_90d_rate", domain="Macro", kind="level")
    meli = evidence(eid="meli", metric="npl_15_90_total", domain="Fintech", kind="level")
    derived = evidence(eid="linked", metric="fintech_mau_yoy_growth", typ="INTERPRETATION", source_ids='["bcb","meli"]')
    with pytest.raises(ValueError, match="definitions are incompatible"):
        build_swot(registry(bcb, meli, derived))