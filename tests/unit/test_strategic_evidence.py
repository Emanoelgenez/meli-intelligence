"""Offline contracts for source-backed strategic preparation (no production I/O)."""
from io import BytesIO
import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from meli_intelligence.evidence.strategic import (
    LINEAGE_SCHEMA, adapt_financial_strategic_evidence, adapt_operational_strategic_evidence,
    adapt_macro_strategic_evidence, build_strategic_evidence, validate_derivation_lineage,
)
from meli_intelligence.evidence.adapters import adapt_financial_evidence, adapt_macro_evidence
from meli_intelligence.evidence.model import normalize_evidence
from meli_intelligence.storage.evidence import _SCHEMA
from meli_intelligence.storage.macro_analytics import MACRO_EVIDENCE_SCHEMA, write_macro_evidence, read_macro_evidence
from meli_intelligence.analytics.macro import build_macro_analytics
from meli_intelligence.analytics.macro_evidence import build_macro_observations
from meli_intelligence.strategy.pestel import build_pestel, validate_pestel_lineage
from meli_intelligence.strategy.swot import build_swot, validate_swot_lineage


def company(metric="net_revenues_financial_income", values=(100., 120.), **changes):
    instant = metric == "fintech_mau"
    unit = "users" if metric in {"fintech_mau", "unique_active_buyers"} else "USD"
    return pd.DataFrame([dict(dict(
        entity_cik="0000000001", entity_name="Fixture Inc.", metric_id=metric,
        period_start=None if instant else f"{year}-01-01", period_end=f"{year}-03-31",
        reference_year=year, period_type="INSTANT" if instant else "QUARTER", period_label="Q1",
        value=value, unit=unit, definition_version="v1", source="SEC fixture",
        accession_number=f"fixture-{year}", filing_date=f"{year}-05-01",
    ), **changes) for year, value in zip((2023, 2024), values)])


def macro_row(metric, ref, value, unit="percent_per_year", frequency="daily"):
    return dict(metric_id=metric, reference_date=ref, value=value, unit=unit, frequency=frequency,
                source="Official fixture", source_series_id="fixture:"+metric,
                source_url="https://example.invalid/"+metric, retrieved_at="2024-04-01T00:00:00Z", ingestion_version="1")


def macro():
    return pd.DataFrame([
        macro_row("selic_target_annual", "2024-01-01", 10.),
        macro_row("selic_target_annual", "2024-02-01", 11.),
        macro_row("usd_brl_sell_rate", "2023-12-28", 4.8, "brl_per_usd"),
        macro_row("usd_brl_sell_rate", "2023-12-29", 4.9, "brl_per_usd"),
        macro_row("usd_brl_sell_rate", "2024-01-30", 5., "brl_per_usd"),
        macro_row("ipca_12m_change", "2023-12-31", 5., "percent", "monthly"),
        macro_row("ipca_12m_change", "2024-01-31", 5.2, "percent", "monthly"),
    ])


@pytest.mark.parametrize("metric,adapter", [("net_revenues_financial_income", adapt_financial_strategic_evidence),
    ("gmv", adapt_operational_strategic_evidence), ("unique_active_buyers", adapt_operational_strategic_evidence),
    ("fintech_mau", adapt_operational_strategic_evidence), ("tpv", adapt_operational_strategic_evidence)])
def test_company_determinism_lineage_and_native_periods(metric, adapter):
    facts = company(metric)
    before = facts.copy(deep=True)
    result = adapter(facts)
    pd.testing.assert_frame_equal(facts, before)
    repeated = adapter(facts.iloc[::-1])
    pd.testing.assert_frame_equal(result.registry, repeated.registry)
    pd.testing.assert_frame_equal(result.lineage, repeated.lineage)
    derived = result.registry.loc[result.registry.metric_id.str.endswith("_yoy_growth")].iloc[0]
    assert derived.value == pytest.approx(20.) and derived.unit == "percent"
    assert derived.evidence_type == "OBSERVATION" and not derived.is_interpretation
    assert set(result.lineage.role) == {"current", "previous"}
    linked = result.registry.set_index("evidence_id").loc[result.lineage.source_evidence_id]
    assert set(pd.to_datetime(linked.reference_date).dt.year) == {2023, 2024}
    assert len(json.loads(derived.source_evidence_ids)) == 1
    validate_derivation_lineage(result.registry, result.lineage)
    if adapter is adapt_financial_strategic_evidence:
        assert set(adapt_financial_evidence(facts).evidence_id).issubset(set(result.registry.evidence_id))


@pytest.mark.parametrize("field,value", [("reference_year", 2000), ("unit", "BRL"),
    ("period_start", "2025-01-01"), ("scope", "P2P"), ("business_domain", "Macro"),
    ("value", float("nan")), ("value", float("inf"))])
def test_invalid_financial_inputs_are_rejected(field, value):
    facts = company()
    facts.loc[1, field] = value
    with pytest.raises(ValueError):
        adapt_financial_strategic_evidence(facts)


@pytest.mark.parametrize("adapter,metric", [(adapt_financial_strategic_evidence, "net_revenues_financial_income"),
                                           (adapt_operational_strategic_evidence, "tpv")])
def test_duplicates_and_missing_columns_are_explicit(adapter, metric):
    facts = company(metric)
    with pytest.raises(ValueError, match="unique"):
        adapter(pd.concat([facts, facts.iloc[[0]]], ignore_index=True))
    with pytest.raises(ValueError, match="missing columns"):
        adapter(facts.drop(columns="accession_number"))


@pytest.mark.parametrize("change", ["missing", "nonpositive", "calendar", "definition"])
def test_ineligible_comparisons_are_omitted_without_inventing_growth(change):
    facts = company("tpv")
    if change == "missing": facts = facts.iloc[[1]]
    if change == "nonpositive": facts.loc[0,"value"] = 0.
    if change == "calendar": facts.loc[0,"period_start"] = "2023-01-02"
    if change == "definition": facts.loc[1,"definition_version"] = "v2_excludes_p2p"
    result = adapt_operational_strategic_evidence(facts)
    assert result.lineage.empty and len(result.registry) == len(facts)
    assert result.omissions.reason.str.contains("no comparable").all()


def test_recast_excluding_p2p_is_the_only_approved_cross_version_family():
    facts = company("tpv")
    facts["definition_version"] = ["v2_recast_excludes_p2p", "v2_excludes_p2p"]
    result = adapt_operational_strategic_evidence(facts)
    assert len(result.lineage) == 2
    p = build_pestel(result.registry)
    assert len(build_swot(result.registry, p)) == 1


def test_entities_never_cross_join_and_domain_is_metric_specific():
    facts = pd.concat([company("gmv"), company("gmv", values=(1000., 900.), entity_cik="0000000002", entity_name="Other Inc.")])
    result = adapt_operational_strategic_evidence(facts)
    derived = result.registry.loc[result.registry.metric_id.eq("gmv_yoy_growth")]
    assert sorted(round(x) for x in derived.value) == [-10, 20]
    assert set(result.registry.business_domain) == {"Commerce"}


@pytest.mark.parametrize("mutation", ["orphan", "missing", "duplicate", "value", "period", "domain", "definition", "support"])
def test_lineage_audit_rejects_tampering(mutation):
    result = adapt_operational_strategic_evidence(company("tpv"))
    r, edges = result.registry.copy(), result.lineage.copy()
    child = r.index[r.metric_id.eq("tpv_yoy_growth")][0]
    prior_id = edges.loc[edges.role.eq("previous"),"source_evidence_id"].iloc[0]
    prior = r.index[r.evidence_id.eq(prior_id)][0]
    if mutation == "orphan": edges.loc[0,"source_evidence_id"] = "unknown"
    if mutation == "missing": edges = edges.iloc[:1]
    if mutation == "duplicate": edges = pd.concat([edges, edges.iloc[[0]]])
    if mutation == "value": r.loc[child,"value"] = 99.
    if mutation == "period": r.loc[prior,"period_start"] = pd.Timestamp("2023-01-02").date()
    if mutation == "domain": r.loc[prior,"business_domain"] = "Macro"
    if mutation == "definition": r.loc[prior,"definition_context"] = "definition_version=p2p"
    if mutation == "support": r.loc[child,"source_evidence_ids"] = json.dumps([prior_id])
    with pytest.raises(ValueError): validate_derivation_lineage(r, edges)


def test_macro_numeric_transport_and_versioned_schema_roundtrip(tmp_path):
    facts = macro()
    analytics = build_macro_analytics(facts)
    observations = build_macro_observations(facts, analytics)
    common = adapt_macro_evidence(observations)
    expected = observations.set_index("evidence_id")
    for row in common.itertuples():
        assert (row.value, row.unit, row.frequency) == tuple(expected.loc[row.evidence_id, ["value","unit","frequency"]])
    path = tmp_path / "macro_evidence.parquet"
    write_macro_evidence(observations, path=path)
    write_macro_evidence(observations, path=path)
    restored = read_macro_evidence(path)
    assert list(restored.columns) == MACRO_EVIDENCE_SCHEMA.names
    assert restored.set_index("evidence_id").value.to_dict() == observations.set_index("evidence_id").value.to_dict()
    assert json.loads(path.with_suffix(".parquet.metadata.json").read_text())["schema_version"] == "2"
    with pytest.raises(ValueError, match="missing columns"):
        build_macro_observations(facts.drop(columns="frequency"), analytics)


def test_macro_strategic_temporal_series_lineage_and_determinism():
    facts = macro()
    result = adapt_macro_strategic_evidence(facts)
    other = adapt_macro_strategic_evidence(facts.iloc[::-1])
    pd.testing.assert_frame_equal(result.registry, other.registry)
    pd.testing.assert_frame_equal(result.lineage, other.lineage)
    validate_derivation_lineage(result.registry, result.lineage)
    assert result.lineage.source_series_id.notna().all()
    p = build_pestel(result.registry)
    s = build_swot(result.registry, p)
    assert set(p.pestel_dimension) == {"ECONOMIC"}
    assert s.swot_category.tolist() == ["THREAT"]
    validate_swot_lineage(s, result.registry, p)


@pytest.mark.parametrize("field,value", [("unit","USD"), ("frequency","monthly"), ("source_series_id","different"), ("value",float("nan"))])
def test_macro_incompatible_or_missing_inputs_fail(field, value):
    f = macro(); f.loc[1,field] = value
    with pytest.raises(ValueError): adapt_macro_strategic_evidence(f)


def test_macro_pix_does_not_invent_technology_adoption_to_satisfy_swot():
    f = pd.DataFrame([macro_row("pix_transactions_count_monthly", "2023-03-31", 100., "transactions", "monthly"),
                      macro_row("pix_transactions_count_monthly", "2024-03-31", 120., "transactions", "monthly")])
    result = adapt_macro_strategic_evidence(f)
    p = build_pestel(result.registry)
    assert set(p.pestel_dimension) == {"ECONOMIC"}
    assert not result.registry.definition_context.str.contains("technology_adoption").any()
    with pytest.raises(ValueError, match="compatible PESTEL lineage"):
        build_swot(result.registry, p)


def test_integrated_registry_strategy_and_arrow_roundtrip_in_memory():
    result = build_strategic_evidence(financial=company(), operational_kpis=company("fintech_mau"), macro=macro())
    r = normalize_evidence(result.registry)
    assert r.evidence_id.is_unique
    p = build_pestel(r); validate_pestel_lineage(p, r)
    s = build_swot(r,p); validate_swot_lineage(s,r,p)
    assert set(p.pestel_dimension) == {"ECONOMIC","SOCIAL"}
    assert s.swot_category.value_counts().to_dict() == {"STRENGTH":2,"THREAT":1}
    for frame, schema in ((r, _SCHEMA), (result.lineage, LINEAGE_SCHEMA)):
        table = pa.Table.from_pandas(frame,schema=schema,preserve_index=False,safe=True)
        buffer = BytesIO(); pq.write_table(table,buffer)
        assert pq.read_table(BytesIO(buffer.getvalue())).equals(table)


def test_missing_inputs_return_explicit_omissions_and_empty_schemas():
    result = build_strategic_evidence()
    assert result.registry.empty and result.lineage.empty
    assert len(result.omissions) == 3


@pytest.mark.parametrize("mutation", ["series", "reference_date", "unit", "frequency", "operation"])
def test_macro_lineage_rejects_invalid_metadata_and_calendar(mutation):
    result = adapt_macro_strategic_evidence(macro())
    r, edges = result.registry.copy(), result.lineage.copy()
    child = r.index[r.metric_id.eq("selic_target_change_pp")][0]
    if mutation == "series": edges.loc[0,"source_series_id"] = "unknown"
    elif mutation == "operation": edges.loc[edges.observation_id.eq(r.loc[child,"evidence_id"]),"operation"] = "percent_change"
    elif mutation == "reference_date": r.loc[child,"reference_date"] = pd.Timestamp("2024-02-02").date()
    else: r.loc[child,mutation] = "invalid"
    with pytest.raises(ValueError): validate_derivation_lineage(r, edges)


def test_source_revisions_change_derived_identity_even_when_growth_is_unchanged():
    a = adapt_operational_strategic_evidence(company("gmv"))
    b = adapt_operational_strategic_evidence(company("gmv", values=(200., 240.)))
    assert a.registry.loc[a.registry.metric_id.eq("gmv_yoy_growth"),"evidence_id"].iloc[0] != b.registry.loc[b.registry.metric_id.eq("gmv_yoy_growth"),"evidence_id"].iloc[0]
    f = macro()
    first = adapt_macro_strategic_evidence(f)
    f.loc[f.metric_id.eq("selic_target_annual"),"value"] += 1.
    second = adapt_macro_strategic_evidence(f)
    assert first.registry.loc[first.registry.metric_id.eq("selic_target_change_pp"),"evidence_id"].iloc[0] != second.registry.loc[second.registry.metric_id.eq("selic_target_change_pp"),"evidence_id"].iloc[0]


def test_same_calendar_shape_cannot_hide_different_duration_years():
    facts = company()
    facts.loc[1, "period_start"] = "2022-01-01"
    with pytest.raises(ValueError, match="duration years"):
        adapt_financial_strategic_evidence(facts)


def test_macro_identity_preserves_precision_beyond_formatted_claim():
    f = pd.DataFrame([macro_row("selic_target_annual", "2024-01-01", 1.)])
    a = build_macro_observations(f, build_macro_analytics(f))
    f.loc[0,"value"] = 1.000000000000001
    b = build_macro_observations(f, build_macro_analytics(f))
    assert a.claim.iloc[0] == b.claim.iloc[0]
    assert a.evidence_id.iloc[0] != b.evidence_id.iloc[0]


def test_legacy_macro_schema_requires_reviewed_rebuild(tmp_path):
    f = macro()
    observations = build_macro_observations(f, build_macro_analytics(f))
    legacy = observations.drop(columns=["value", "unit", "frequency"])
    path = tmp_path / "legacy.parquet"
    pq.write_table(pa.Table.from_pandas(legacy,preserve_index=False),path)
    with pytest.raises(ValueError, match="schema mismatch"):
        read_macro_evidence(path)


@pytest.mark.parametrize("key", ["definition", "cohort", "scope"])
def test_financial_semantic_definition_changes_cannot_form_yoy(key):
    facts = company()
    facts["definition_context"] = [f"{key}=v1", f"{key}=v2"]
    with pytest.raises(ValueError, match="definitions"):
        adapt_financial_strategic_evidence(facts)
