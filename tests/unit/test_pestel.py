import json
from datetime import date
import pandas as pd
import pytest
import pyarrow.parquet as pq
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS,normalize_evidence
from meli_intelligence.strategy.pestel import (
 PESTEL_COLUMNS,build_pestel,validate_pestel,validate_pestel_lineage,_pestel_id)
from meli_intelligence.storage.pestel import write_pestel
from meli_intelligence.query.pestel import query_pestel

def row(eid="e1",metric="selic_target_change_pp",domain="Macro",kind="decrease",typ="OBSERVATION",claim="Selic declined 0.5 p.p.",context="reported"):
 return dict(evidence_id=eid,evidence_type=typ,business_domain=domain,entity="Brazil",metric_id=metric,
 reference_date=date(2024,1,31),period_start=None,period_end=date(2024,1,31),period_type="MONTH",period_label="2024-01",
 value=-.5,unit="percentage_points",frequency="monthly",claim=claim,claim_kind=kind,source="BCB",
 source_url=None,filing_date=None,accession_number=None,source_bronze_file=None,source_content_sha256=None,
 source_metric_id=metric,source_evidence_ids="[]",is_interpretation=typ=="INTERPRETATION",
 methodology_version="1",definition_context=context)
def registry(*rows):return normalize_evidence(pd.DataFrame(rows,columns=EVIDENCE_COLUMNS))
@pytest.mark.parametrize("metric",["selic_target_change_pp","ipca_12m_change_pp","usd_brl_monthly_change_pct","unemployment_rate_change_pp","household_free_credit_balance_yoy_growth","pix_transactions_count_yoy_growth"])
def test_macro_signals_classified_economic(metric):
 out=build_pestel(registry(row(metric=metric)))
 assert len(out)==1 and out.pestel_dimension.iloc[0]=="ECONOMIC"
def test_retail_classified_economic():
 assert build_pestel(registry(row(metric="retail_sales_volume_mom_sa"))).pestel_dimension.tolist()==["ECONOMIC"]
def test_selic_official_fact_can_be_economic():
 assert build_pestel(registry(row(metric="selic_target_annual",typ="FACT",kind="level"))).pestel_dimension.iloc[0]=="ECONOMIC"
@pytest.mark.parametrize("metric,domain", [("fintech_mau_yoy_growth","Fintech"),("unique_active_buyers_yoy_growth","Commerce")])
def test_user_base_and_buyer_growth_classified_social(metric,domain):
 out=build_pestel(registry(row(metric=metric,domain=domain,kind="growth")))
 assert out.pestel_dimension.tolist()==["SOCIAL"]
def test_macro_pix_defaults_economic():
 assert build_pestel(registry(row(metric="pix_transactions_count_yoy_growth",domain="Macro",kind="yoy_growth"))).pestel_dimension.iloc[0]=="ECONOMIC"
def test_pix_technological_requires_explicit_adoption_tag():
 r=row(metric="pix_transactions_count_monthly",domain="Macro",kind="technology_adoption",context="technology_adoption;explicit_digital_infrastructure")
 assert build_pestel(registry(r)).pestel_dimension.tolist()==["TECHNOLOGICAL"]
@pytest.mark.parametrize("kind,dimension", [("public_policy","POLITICAL"),("regulatory_requirement","LEGAL"),("environmental_measurement","ENVIRONMENTAL")])
def test_structured_policy_legal_environmental_evidence_can_be_classified(kind,dimension):
 out=build_pestel(registry(row(metric="explicit_source_measure",domain="PublicInstitution",kind=kind)))
 assert out.pestel_dimension.tolist()==[dimension]
@pytest.mark.parametrize("metric",["unclassified_policy","unclassified_environment","unclassified_legal"])
def test_no_forced_political_environmental_or_legal_coverage(metric):
 out=build_pestel(registry(row(metric=metric,domain="Macro",kind="level")))
 assert out.empty
def test_invalid_dimension_rejected():
 f=build_pestel(registry(row()));f.loc[0,"pestel_dimension"]="SWOT"
 with pytest.raises(ValueError,match="Invalid PESTEL dimensions"):validate_pestel(f)
def test_id_is_deterministic_for_same_classification():
 a=_pestel_id("ECONOMIC","claim",["e1"],date(2024,1,31))
 b=_pestel_id("ECONOMIC","claim",["e1"],date(2024,1,31))
 assert a==b
def test_id_changes_when_dimension_or_evidence_changes():
 base=_pestel_id("ECONOMIC","claim",["e1"],date(2024,1,31))
 assert base!=_pestel_id("SOCIAL","claim",["e1"],date(2024,1,31))
 assert base!=_pestel_id("ECONOMIC","claim",["e2"],date(2024,1,31))
def test_unknown_source_evidence_id_fails():
 source=row(eid="interp",typ="INTERPRETATION",metric="selic_target_change_pp")
 source["source_evidence_ids"]='["missing"]'
 with pytest.raises(ValueError,match="Unknown source_evidence_id"):build_pestel(registry(source))
def test_interpretation_lineage_types_and_claim_are_preserved():
 original=row(eid="obs",claim="Selic target was reported at 11%.",kind="level")
 interp=row(eid="interp",typ="INTERPRETATION",claim="The Selic target declined versus the previous observation.",kind="reported_selic_decline")
 interp["source_evidence_ids"]='["obs"]'
 out=build_pestel(registry(original,interp))
 item=out.loc[out.is_interpretation].iloc[0]
 assert item.claim=="The Selic target declined versus the previous observation."
 assert bool(item.is_interpretation) is True
 assert json.loads(item.source_evidence_ids)==["interp","obs"]
 assert json.loads(item.source_evidence_types)==["INTERPRETATION","OBSERVATION"]
def test_fact_observation_interpretation_types_are_accepted():
 f=row(eid="fact",typ="FACT",metric="selic_target_annual",kind="level")
 o=row(eid="obs",typ="OBSERVATION",metric="selic_target_annual",kind="level")
 i=row(eid="interp",typ="INTERPRETATION",metric="selic_target_annual",kind="level")
 i["source_evidence_ids"]='["obs"]'
 assert {t for encoded in build_pestel(registry(f,o,i)).source_evidence_types for t in json.loads(encoded)}=={"FACT","OBSERVATION","INTERPRETATION"}
def test_rationale_domain_and_source_are_populated():
 x=build_pestel(registry(row())).iloc[0]
 assert x.classification_rationale and x.pestel_dimension=="ECONOMIC" and x.source=="BCB"
def test_claim_text_is_not_rewritten():
 original=row(claim="Official measure was 1.2 in the period.")
 assert build_pestel(registry(original)).claim.iloc[0]==original["claim"]
def test_output_blocks_prescriptive_or_causal_claims():
 for text in ("This is an opportunity.","This caused a product change.","We recommend a feature solution.","This is a threat, strength, and weakness."):
  with pytest.raises(ValueError,match="prohibited|causal or prescriptive"):
   build_pestel(registry(row(claim=text)))
def test_ordering_is_deterministic():
 a=row(eid="b",metric="ipca_12m_change_pp");b=row(eid="a",metric="selic_target_change_pp")
 x=build_pestel(registry(a,b));y=build_pestel(registry(b,a))
 assert x.pestel_id.tolist()==y.pestel_id.tolist()
def test_schema_and_unique_ids():
 out=build_pestel(registry(row(eid="a"),row(eid="b")))
 assert list(out.columns)==PESTEL_COLUMNS and out.pestel_id.is_unique
def test_lineage_validator_rejects_unknown_id():
 out=build_pestel(registry(row()))
 out.loc[0,"source_evidence_ids"]='["unknown"]'
 with pytest.raises(ValueError,match="Unknown source_evidence_id"):validate_pestel_lineage(out,registry(row()))
def test_storage_roundtrip_replay_conflict_and_zstd(tmp_path):
 r=registry(row());out=build_pestel(r);p=tmp_path/"pestel.parquet"
 write_pestel(out,p);write_pestel(out,p)
 assert pq.read_metadata(p).row_group(0).column(0).compression=="ZSTD"
 conflict=out.copy();conflict.loc[0,"claim"]="Different claim"
 with pytest.raises(ValueError,match="identity conflict"):write_pestel(conflict,p)
def test_query_dimension_domain_metric_and_source_evidence(tmp_path):
 r=registry(row(metric="selic_target_change_pp",domain="Macro"),row(eid="social",metric="fintech_mau_yoy_growth",domain="Fintech",kind="growth"))
 out=build_pestel(r);p=tmp_path/"pestel.parquet";write_pestel(out,p)
 assert len(query_pestel(path=p,pestel_dimension="ECONOMIC"))==1
 assert len(query_pestel(path=p,business_domain="Fintech"))==1
 economic=out.loc[out.pestel_dimension=="ECONOMIC"].iloc[0]
 assert len(query_pestel(path=p,source_evidence_id="e1"))==1
 assert len(query_pestel(path=p,metric_id="selic_target_change_pp"))==1
def test_query_rejects_invalid_dimension():
 with pytest.raises(ValueError,match="Invalid PESTEL dimension"):
  query_pestel(path="not-used.parquet",pestel_dimension="SWOT")
def test_missing_optional_metric_id_is_omitted():
 r=row();r["metric_id"]=None
 assert build_pestel(registry(r)).empty


def test_valid_dimension_with_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError, match="PESTEL Parquet not found"):
        query_pestel(path="not-used.parquet", pestel_dimension="ECONOMIC")
