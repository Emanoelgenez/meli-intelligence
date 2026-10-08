from datetime import date
import json

import pandas as pd
import pytest

from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence
from meli_intelligence.product.evidence import (
    DISCOVERY_THEMES,
    PRODUCT_EVIDENCE_COLUMNS,
    PRODUCT_EVIDENCE_TYPES,
    build_product_evidence,
    validate_product_evidence,
    validate_product_evidence_lineage,
)
from meli_intelligence.query.product_evidence import query_product_evidence
from meli_intelligence.storage.product_evidence import write_product_evidence
from meli_intelligence.strategy.pestel import build_pestel
from meli_intelligence.strategy.swot import build_swot


def evidence(
    eid, metric, domain, *, typ="OBSERVATION", reference_date=date(2024, 3, 31),
    period_type="QUARTER", period_label="Q1 2024", context="definition_version=v1",
    source_ids="[]", value=4.0, kind="yoy_growth", claim=None,
):
    return {
        "evidence_id": eid, "evidence_type": typ, "business_domain": domain,
        "entity": "MercadoLibre", "metric_id": metric, "reference_date": reference_date,
        "period_start": date(2024, 1, 1), "period_end": reference_date,
        "period_type": period_type, "period_label": period_label, "value": value,
        "unit": "percent", "frequency": "quarterly", "claim": claim or f"{metric} was reported for {period_label}.",
        "claim_kind": kind, "source": "official source", "source_url": None,
        "filing_date": None, "accession_number": None, "source_bronze_file": None,
        "source_content_sha256": None, "source_metric_id": metric,
        "source_evidence_ids": source_ids, "is_interpretation": typ == "INTERPRETATION",
        "methodology_version": "1", "definition_context": context,
    }


def registry(*rows):
    return normalize_evidence(pd.DataFrame(rows, columns=EVIDENCE_COLUMNS))


def cross_domain_registry(*, commerce_metric="gmv_yoy_growth", fintech_metric="fintech_mau_yoy_growth", **kwargs):
    return registry(
        evidence("commerce-evidence", commerce_metric, "Commerce", **kwargs),
        evidence("fintech-evidence", fintech_metric, "Fintech", **kwargs),
    )


def test_supported_types_and_theme_are_small_allowlists():
    assert PRODUCT_EVIDENCE_TYPES == {"HYPOTHESIS", "QUESTION_FOR_PRODUCT_DISCOVERY"}
    assert DISCOVERY_THEMES == {"ECOSYSTEM_ENGAGEMENT"}


def test_compatible_commerce_fintech_pair_builds_hypothesis_and_question():
    reg = cross_domain_registry()
    result = build_product_evidence(reg)
    assert set(result.product_evidence_type) == {"HYPOTHESIS", "QUESTION_FOR_PRODUCT_DISCOVERY"}
    hypothesis = result.loc[result.product_evidence_type == "HYPOTHESIS"].iloc[0]
    question = result.loc[result.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY"].iloc[0]
    assert hypothesis.discovery_theme == "ECOSYSTEM_ENGAGEMENT"
    assert json.loads(hypothesis.source_evidence_ids) == ["commerce-evidence", "fintech-evidence"]
    assert hypothesis.product_evidence_id in json.loads(question.source_hypothesis_ids)
    assert hypothesis.business_domain == "Ecosystem"


def test_commerce_only_does_not_force_hypothesis():
    assert build_product_evidence(registry(evidence("buyers", "unique_active_buyers_yoy_growth", "Commerce"))).empty


def test_fintech_only_does_not_force_hypothesis():
    assert build_product_evidence(registry(evidence("mau", "fintech_mau_yoy_growth", "Fintech"))).empty


def test_cross_domain_rule_accepts_each_allowlisted_metric_pair():
    for commerce_metric in ("unique_active_buyers_yoy_growth", "gmv_yoy_growth"):
        for fintech_metric in ("fintech_mau_yoy_growth", "tpv_yoy_growth"):
            result = build_product_evidence(cross_domain_registry(commerce_metric=commerce_metric, fintech_metric=fintech_metric))
            assert len(result) == 2


def test_hypothesis_explicitly_preserves_aggregate_data_limitation():
    result = build_product_evidence(cross_domain_registry())
    hypothesis = result.loc[result.product_evidence_type == "HYPOTHESIS"].iloc[0]
    assert "may" in hypothesis.statement
    assert "do not establish user-level overlap" in hypothesis.statement
    assert "user-level validation" in hypothesis.statement
    assert "aggregate_metrics_only" in hypothesis.definition_context
    assert "no_user_level_overlap_inference" in hypothesis.definition_context
    assert "cross_domain_user_overlap" not in set(json.loads(hypothesis.source_metric_ids))
    assert "ecosystemic_users" not in set(json.loads(hypothesis.source_metric_ids))


def test_cross_domain_populations_may_differ_without_implying_user_overlap():
    reg = registry(
        evidence(
            "buyers-population",
            "unique_active_buyers_yoy_growth",
            "Commerce",
            context="definition_version=v1;population=reported_active_buyers",
        ),
        evidence(
            "mau-population",
            "fintech_mau_yoy_growth",
            "Fintech",
            context="definition_version=v1;population=reported_fintech_mau",
        ),
    )

    result = build_product_evidence(reg)

    assert len(result) == 2
    assert result.product_evidence_type.value_counts().to_dict() == {
        "HYPOTHESIS": 1,
        "QUESTION_FOR_PRODUCT_DISCOVERY": 1,
    }
    hypothesis = result.loc[result.product_evidence_type == "HYPOTHESIS"].iloc[0]
    assert "aggregate" in hypothesis.statement
    assert "do not establish user-level overlap" in hypothesis.statement
    assert "user-level validation" in hypothesis.statement
    assert "population=reported_active_buyers" in hypothesis.definition_context
    assert "population=reported_fintech_mau" in hypothesis.definition_context


def test_population_conflict_within_same_metric_lineage_is_rejected():
    reg = registry(
        evidence(
            "buyers-observation",
            "unique_active_buyers_yoy_growth",
            "Commerce",
            context="definition_version=v1;population=reported_active_buyers",
        ),
        evidence(
            "buyers-interpretation",
            "unique_active_buyers_yoy_growth",
            "Commerce",
            typ="INTERPRETATION",
            source_ids='["buyers-observation"]',
            context="definition_version=v1;population=active_buyers_redefined",
        ),
        evidence(
            "mau-observation",
            "fintech_mau_yoy_growth",
            "Fintech",
            context="definition_version=v1;population=reported_fintech_mau",
        ),
    )

    with pytest.raises(ValueError, match="definitions are incompatible.*population"):
        build_product_evidence(reg)


def test_question_is_open_and_does_not_embed_a_solution():
    result = build_product_evidence(cross_domain_registry())
    question = result.loc[result.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY"].iloc[0]
    assert question.statement.startswith("How ") and question.statement.endswith("?")
    assert "feature" not in question.statement.casefold()
    assert "cashback" not in question.statement.casefold()
    assert "solution" not in question.statement.casefold()


def test_question_orphan_and_unknown_hypothesis_are_rejected():
    result = build_product_evidence(cross_domain_registry())
    question = result.loc[result.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY"]
    with pytest.raises(ValueError, match="Unknown hypothesis IDs"):
        validate_product_evidence(question)
    unknown = result.copy()
    question_index = unknown.index[unknown.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY"][0]
    unknown.loc[question_index, "source_hypothesis_ids"] = '["missing-hypothesis"]'
    with pytest.raises(ValueError, match="Unknown hypothesis IDs"):
        validate_product_evidence(unknown)


def test_unknown_evidence_and_wrong_interpretation_type_are_rejected():
    reg = cross_domain_registry()
    result = build_product_evidence(reg)
    unknown = result.copy()
    unknown["source_evidence_ids"] = '["commerce-evidence","missing-evidence","fintech-evidence"]'
    with pytest.raises(ValueError, match="Unknown Evidence IDs"):
        validate_product_evidence_lineage(unknown, reg)
    wrong_type = result.copy()
    wrong_type["source_interpretation_ids"] = '["commerce-evidence"]'
    with pytest.raises(ValueError, match="must reference INTERPRETATION"):
        validate_product_evidence_lineage(wrong_type, reg)


def test_interpretation_lineage_is_preserved_and_type_checked():
    observation = evidence("gmv-observation", "gmv_yoy_growth", "Commerce", typ="OBSERVATION")
    interpretation = evidence(
        "gmv-interpretation", "gmv_yoy_growth", "Commerce", typ="INTERPRETATION",
        source_ids='["gmv-observation"]',
    )
    mau = evidence("mau-observation", "fintech_mau_yoy_growth", "Fintech")
    reg = registry(observation, interpretation, mau)
    result = build_product_evidence(reg)
    hypothesis = result.loc[result.product_evidence_type == "HYPOTHESIS"].iloc[0]
    assert json.loads(hypothesis.source_interpretation_ids) == ["gmv-interpretation"]
    assert set(json.loads(hypothesis.source_evidence_ids)) == {"gmv-observation", "gmv-interpretation", "mau-observation"}
    validate_product_evidence_lineage(result, reg)


def test_pestel_and_swot_lineage_are_optional_and_preserved_when_compatible():
    reg = cross_domain_registry(commerce_metric="unique_active_buyers_yoy_growth")
    pestel = build_pestel(reg)
    swot = build_swot(reg)
    result = build_product_evidence(reg, pestel=pestel, swot=swot)
    hypothesis = result.loc[result.product_evidence_type == "HYPOTHESIS"].iloc[0]
    assert set(json.loads(hypothesis.source_pestel_ids)) == set(pestel.pestel_id)
    assert set(json.loads(hypothesis.source_swot_ids)) == set(swot.swot_id)
    validate_product_evidence_lineage(result, reg, pestel, swot)


def test_unknown_pestel_and_swot_ids_are_rejected():
    reg = cross_domain_registry(commerce_metric="unique_active_buyers_yoy_growth")
    pestel = build_pestel(reg)
    swot = build_swot(reg)
    result = build_product_evidence(reg, pestel=pestel, swot=swot)
    bad_pestel = result.copy()
    bad_pestel["source_pestel_ids"] = '["missing-pestel"]'
    with pytest.raises(ValueError, match="Unknown PESTEL IDs"):
        validate_product_evidence_lineage(bad_pestel, reg, pestel, swot)
    bad_swot = result.copy()
    bad_swot["source_swot_ids"] = '["missing-swot"]'
    with pytest.raises(ValueError, match="Unknown SWOT IDs"):
        validate_product_evidence_lineage(bad_swot, reg, pestel, swot)


def test_pestel_evidence_mismatch_is_rejected():
    reg = cross_domain_registry(commerce_metric="unique_active_buyers_yoy_growth")
    pestel = build_pestel(reg)
    product = build_product_evidence(reg, pestel=pestel)
    hypothesis = product.loc[product.product_evidence_type == "HYPOTHESIS"].copy()
    hypothesis.loc[:, "source_evidence_ids"] = '["fintech-evidence"]'
    hypothesis.loc[:, "source_metric_ids"] = '["fintech_mau_yoy_growth"]'
    with pytest.raises(ValueError, match="PESTEL Evidence lineage is incompatible"):
        validate_product_evidence_lineage(hypothesis, reg, pestel=pestel)


def test_swot_evidence_mismatch_is_rejected():
    reg = cross_domain_registry(commerce_metric="unique_active_buyers_yoy_growth")
    swot = build_swot(reg)
    product = build_product_evidence(reg, swot=swot)
    hypothesis = product.loc[product.product_evidence_type == "HYPOTHESIS"].copy()
    hypothesis.loc[:, "source_evidence_ids"] = '["fintech-evidence"]'
    hypothesis.loc[:, "source_metric_ids"] = '["fintech_mau_yoy_growth"]'
    with pytest.raises(ValueError, match="SWOT Evidence lineage is incompatible"):
        validate_product_evidence_lineage(hypothesis, reg, swot=swot)


def test_temporal_mismatch_does_not_create_hypothesis():
    reg = registry(
        evidence("commerce", "gmv_yoy_growth", "Commerce", reference_date=date(2024, 3, 31)),
        evidence("fintech", "fintech_mau_yoy_growth", "Fintech", reference_date=date(2023, 12, 31), period_label="Q4 2023"),
    )
    assert build_product_evidence(reg).empty


def test_period_definition_mismatch_is_rejected():
    period_mismatch = registry(
        evidence("commerce", "gmv_yoy_growth", "Commerce", period_type="QUARTER", period_label="Q1 2024"),
        evidence("fintech", "fintech_mau_yoy_growth", "Fintech", period_type="MONTH", period_label="2024-03"),
    )
    with pytest.raises(ValueError, match="periods are incompatible"):
        build_product_evidence(period_mismatch)
    definition_mismatch = registry(
        evidence("commerce", "gmv_yoy_growth", "Commerce", context="definition_version=v1"),
        evidence("fintech", "fintech_mau_yoy_growth", "Fintech", context="definition_version=v2"),
    )
    with pytest.raises(ValueError, match="definitions are incompatible"):
        build_product_evidence(definition_mismatch)


def test_unknown_strategy_lineage_ids_are_rejected():
    reg = cross_domain_registry(commerce_metric="unique_active_buyers_yoy_growth")
    pestel = build_pestel(reg)
    swot = build_swot(reg)
    product = build_product_evidence(reg, pestel=pestel, swot=swot)
    hypothesis = product.loc[product.product_evidence_type == "HYPOTHESIS"].copy()
    hypothesis.loc[:, "source_pestel_ids"] = '["not-in-registry"]'
    with pytest.raises(ValueError, match="Unknown PESTEL IDs"):
        validate_product_evidence_lineage(hypothesis, reg, pestel=pestel, swot=swot)


def test_invalid_type_and_theme_are_rejected():
    result = build_product_evidence(cross_domain_registry())
    invalid = result.copy()
    invalid.loc[0, "product_evidence_type"] = "FEATURE"
    with pytest.raises(ValueError, match="Unsupported Product Evidence types"):
        validate_product_evidence(invalid)
    invalid = result.copy()
    invalid.loc[0, "discovery_theme"] = "RETENTION"
    with pytest.raises(ValueError, match="Unsupported Product discovery themes"):
        validate_product_evidence(invalid)


def test_language_guard_rejects_causality_solution_and_user_need_claims():
    result = build_product_evidence(cross_domain_registry())
    for text in (
        "Commerce growth caused Fintech activity.",
        "We should build a feature.",
        "Users need rewards.",
        "Customers want cashback.",
        "A solution will improve retention.",
    ):
        invalid = result.copy()
        invalid.loc[invalid.product_evidence_type == "HYPOTHESIS", "statement"] = text
        with pytest.raises(ValueError, match="causal, prescriptive"):
            validate_product_evidence(invalid)


def test_deterministic_ids_and_ordering():
    reg = cross_domain_registry()
    a = build_product_evidence(reg)
    b = build_product_evidence(reg.iloc[::-1].reset_index(drop=True))
    assert a.product_evidence_id.tolist() == b.product_evidence_id.tolist()
    assert a.product_evidence_id.is_unique


def test_query_validates_enum_before_filesystem():
    with pytest.raises(ValueError, match="Invalid Product Evidence type"):
        query_product_evidence(path="missing.parquet", product_evidence_type="FEATURE")
    with pytest.raises(FileNotFoundError):
        query_product_evidence(path="missing.parquet", product_evidence_type="HYPOTHESIS")


def test_storage_replay_conflict_and_query_filters(tmp_path):
    reg = cross_domain_registry(commerce_metric="unique_active_buyers_yoy_growth")
    pestel = build_pestel(reg)
    swot = build_swot(reg)
    result = build_product_evidence(reg, pestel=pestel, swot=swot)
    path = tmp_path / "product_evidence.parquet"
    write_product_evidence(result, path)
    write_product_evidence(result, path)
    hypothesis = result.loc[result.product_evidence_type == "HYPOTHESIS"].iloc[0]
    question = result.loc[result.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY"].iloc[0]
    assert len(query_product_evidence(path=path, product_evidence_type="HYPOTHESIS")) == 1
    assert len(query_product_evidence(path=path, discovery_theme="ECOSYSTEM_ENGAGEMENT")) == 2
    assert len(query_product_evidence(path=path, metric_id="unique_active_buyers_yoy_growth")) == 2
    assert len(query_product_evidence(path=path, source_evidence_id="commerce-evidence")) == 2
    assert len(query_product_evidence(path=path, source_pestel_id=json.loads(hypothesis.source_pestel_ids)[0])) == 2
    assert len(query_product_evidence(path=path, source_swot_id=json.loads(hypothesis.source_swot_ids)[0])) == 2
    assert len(query_product_evidence(path=path, source_hypothesis_id=hypothesis.product_evidence_id)) == 1
    conflict = result.copy()
    conflict.loc[conflict.product_evidence_type == "HYPOTHESIS", "rationale"] = "Altered rationale without changing its ID."
    with pytest.raises(ValueError, match="identity conflict"):
        write_product_evidence(conflict, path)
