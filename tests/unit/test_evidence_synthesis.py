from datetime import date
import json
import pandas as pd
import pytest
from meli_intelligence.evidence.adapters import adapt_financial_evidence,adapt_macro_evidence,adapt_operational_evidence,build_evidence_registry
from meli_intelligence.evidence.interpretation import interpret_evidence,validate_interpretation_lineage
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence
from meli_intelligence.storage.evidence import write_evidence_registry,write_interpretations
from meli_intelligence.query.evidence import query_evidence

def macro(metric="pix_transactions_count_yoy_growth",kind="yoy_growth",eid="macro-1",context="reported"):
 return pd.DataFrame([dict(evidence_id=eid,evidence_type="OBSERVATION",business_domain="Macro",metric_id=metric,reference_date=date(2024,1,31),claim="Pix increased 20% YoY.",claim_kind=kind,source="BCB",source_metric_id=metric,is_interpretation=False,definition_context=context)])
def op(metric="fintech_mau_yoy_growth",eid="op-1",value=10,context="v1",ref=date(2024,3,31)):
 return pd.DataFrame([dict(evidence_id=eid,evidence_type="OBSERVATION",business_domain="Fintech",metric_id=metric,reference_date=ref,claim="Fintech MAU grew.",claim_kind="growth",source="SEC",source_metric_id=metric,value=value,unit="percent",definition_context=context)])
def test_macro_adapter_preserves_observation_identity():
 r=adapt_macro_evidence(macro()).iloc[0];assert r.evidence_id=="macro-1" and r.evidence_type=="OBSERVATION" and not r.is_interpretation
def test_operational_adapter_preserves_fact_statement():
 f=pd.DataFrame([dict(evidence_id="sec1",evidence_class="FACT",evidence_type="meli_plus",business_domain="Ecosystem",reference_period="2024-03-31",statement="MELI+ subscribers reached 10 million.",source_url="https://sec.example")])
 r=adapt_operational_evidence(f).iloc[0];assert r.evidence_id=="sec1" and r.claim==f.iloc[0].statement and r.business_domain=="Ecosystem" and r.source_url=="https://sec.example"
def test_financial_adapter_uses_existing_analytics():
 f=pd.DataFrame([dict(metric_id="net_revenues_financial_income_yoy_growth",period_end=date(2024,3,31),period_label="Q1 2024",value=20.,unit="percent",formula="existing",source_metrics="net_revenues_financial_income")])
 r=adapt_financial_evidence(f).iloc[0];assert r.metric_id==f.iloc[0].metric_id and r.value==20
def test_common_schema_ids_and_sorting():
 r=build_evidence_registry(macro=macro(eid="z"),operational=op(eid="a"));assert list(r.columns)==EVIDENCE_COLUMNS and r.evidence_id.is_unique and r.evidence_id.tolist()==["z","a"]
def test_cross_source_id_collision_fails():
 with pytest.raises(ValueError,match="collision"):build_evidence_registry(macro=macro(eid="same"),operational=op(eid="same"))
def test_macro_is_not_relabelled_as_fact():
 assert adapt_macro_evidence(macro()).iloc[0].evidence_type=="OBSERVATION"
def test_deterministic_interpretation_is_explicit_noncausal():
 r=build_evidence_registry(macro=macro(),financial=pd.DataFrame([dict(metric_id="net_revenues_financial_income_yoy_growth",period_end=date(2024,3,31),value=8,unit="percent",source_metrics="net_revenues_financial_income")]))
 out=interpret_evidence(r);assert out.evidence_type.eq("INTERPRETATION").all() and out.is_interpretation.all()
 assert not out.claim.str.contains(r"cause|because|led to|explains|recommend|feature|solution",case=False,regex=True).any()
def test_interpretation_ids_deterministic_and_source_sensitive():
 r=build_evidence_registry(macro=macro());a=interpret_evidence(r);b=interpret_evidence(r);assert a.evidence_id.tolist()==b.evidence_id.tolist()
 c=r.copy();c.loc[0,"evidence_id"]="new-source";assert a.evidence_id.iloc[0]!=interpret_evidence(c).evidence_id.iloc[0]
def test_lineage_required_and_unknown_id_fails():
 r=build_evidence_registry(macro=macro());i=interpret_evidence(r);assert i.source_evidence_ids.iloc[0]=='["macro-1"]';validate_interpretation_lineage(i,r)
 i.loc[0,"source_evidence_ids"]='["missing"]'
 with pytest.raises(ValueError,match="Unknown source_evidence_id"):validate_interpretation_lineage(i,r)
def test_nonallowlisted_credit_npl_comparison_creates_no_interpretation():
 r=build_evidence_registry(macro=macro("household_free_credit_npl_90d_yoy_change_pp","increase"))
 assert interpret_evidence(r).empty
def test_multi_evidence_allowed_pair_and_lineage():
 r=adapt_operational_evidence(pd.concat([op("fintech_mau_yoy_growth","mau"),op("tpv_yoy_growth","tpv")],ignore_index=True))
 i=interpret_evidence(r,multi_evidence_groups=[["mau","tpv"]])
 assert len(i)==2
 multi=i.loc[i.source_evidence_ids.map(lambda value:len(json.loads(value))==2)]
 assert len(multi)==1
 row=multi.iloc[0]
 assert set(json.loads(row.source_evidence_ids))=={"mau","tpv"}
 assert row.evidence_type=="INTERPRETATION"
 assert bool(row.is_interpretation) is True
 assert "both increased" in row.claim
def test_multi_evidence_definition_and_period_mismatch_fail():
 r=adapt_operational_evidence(pd.concat([op("fintech_mau_yoy_growth","mau"),op("tpv_yoy_growth","tpv")],ignore_index=True))
 x=r.copy();x.loc[x.evidence_id=="tpv","definition_context"]="v2"
 with pytest.raises(ValueError,match="definitions"):interpret_evidence(x,multi_evidence_groups=[["mau","tpv"]])
 x=r.copy();x.loc[x.evidence_id=="tpv","reference_date"]=date(2024,6,30)
 with pytest.raises(ValueError,match="periods"):interpret_evidence(x,multi_evidence_groups=[["mau","tpv"]])
def test_unknown_source_id_fails():
 r=adapt_operational_evidence(op())
 with pytest.raises(ValueError,match="Unknown source_evidence_id"):interpret_evidence(r,multi_evidence_groups=[["missing","op-1"]])
def test_replay_storage_query_and_conflict(tmp_path):
 r=build_evidence_registry(macro=macro());p=tmp_path/"e.parquet";write_evidence_registry(r,p);write_evidence_registry(r,p)
 assert query_evidence(path=p,evidence_type="OBSERVATION",business_domain="Macro").evidence_id.tolist()==["macro-1"]
 x=r.copy();x.loc[0,"claim"]="changed"
 with pytest.raises(ValueError,match="identity conflict"):write_evidence_registry(x,p)
def test_interpretation_storage_and_type_guard(tmp_path):
 r=build_evidence_registry(macro=macro());i=interpret_evidence(r);p=tmp_path/"i.parquet";write_interpretations(i,p)
 assert query_evidence(path=p,evidence_type="INTERPRETATION").evidence_id.tolist()==i.evidence_id.tolist()
 with pytest.raises(ValueError,match="INTERPRETATION rows only"):write_interpretations(r,p)
def test_query_source_evidence_id_filter(tmp_path):
 r=build_evidence_registry(macro=macro());p=tmp_path/"e.parquet";write_evidence_registry(r,p)
 assert query_evidence(path=p,source_evidence_id="absent").empty

def test_registry_without_sources_returns_fixed_empty_schema():
 from meli_intelligence.evidence.adapters import build_evidence_registry
 assert list(build_evidence_registry().columns)==EVIDENCE_COLUMNS
def test_financial_adapter_preserves_original_evidence_id():
 f=pd.DataFrame([dict(evidence_id="filing-fact",evidence_type="FACT",metric_id="cash",period_end=date(2024,3,31),claim="Cash was reported.",source="10-Q")])
 assert adapt_financial_evidence(f).evidence_id.tolist()==["filing-fact"]
def test_macro_adapter_rejects_non_observations():
 f=macro();f.loc[0,"evidence_type"]="HYPOTHESIS"
 with pytest.raises(ValueError,match="Macro adapter accepts OBSERVATION rows only"):
  adapt_macro_evidence(f)
def test_common_model_rejects_hypothesis():
 f=adapt_macro_evidence(macro())
 f.loc[0,"evidence_type"]="HYPOTHESIS"
 with pytest.raises(ValueError,match="Unsupported evidence types"):
  normalize_evidence(f)
def test_selic_interpretation_requires_decline_claim_kind():
 falling=macro("selic_target_change_pp","decrease","selic-fall")
 rising=macro("selic_target_change_pp","increase","selic-rise")
 assert len(interpret_evidence(adapt_macro_evidence(falling)))==1
 assert interpret_evidence(adapt_macro_evidence(rising)).empty
def test_causal_or_prescriptive_interpretation_text_is_blocked():
 from meli_intelligence.evidence.interpretation import _record
 row=adapt_macro_evidence(macro()).iloc[0]
 with pytest.raises(ValueError,match="causal or prescriptive"):
  _record([row],"Pix growth caused a change.","bad","other")
def test_multi_evidence_period_label_mismatch_fails():
 f=pd.concat([op("fintech_mau_yoy_growth","mau"),op("tpv_yoy_growth","tpv")],ignore_index=True)
 f["period_type"]="QUARTER";f["period_label"]=["Q1 2024","Q4 2023"]
 r=adapt_operational_evidence(f)
 with pytest.raises(ValueError,match="period_label"):interpret_evidence(r,multi_evidence_groups=[["mau","tpv"]])
def test_storage_exact_replay_keeps_existing_claim(tmp_path):
 r=build_evidence_registry(macro=macro());p=tmp_path/"evidence.parquet";write_evidence_registry(r,p)
 write_evidence_registry(r,p)
 assert query_evidence(path=p).claim.iloc[0]=="Pix increased 20% YoY."
def test_query_reference_date_range(tmp_path):
 old=macro(eid="jan");old.loc[0,"reference_date"]=date(2024,1,31)
 new=macro(eid="feb");new.loc[0,"reference_date"]=date(2024,2,29)
 p=tmp_path/"evidence.parquet";write_evidence_registry(build_evidence_registry(macro=pd.concat([old,new])),p)
 assert query_evidence(path=p,start_date=date(2024,2,1),end_date=date(2024,2,29)).evidence_id.tolist()==["feb"]
def test_query_rejects_inverted_dates(tmp_path):
 r=build_evidence_registry(macro=macro());p=tmp_path/"e.parquet";write_evidence_registry(r,p)
 with pytest.raises(ValueError,match="start_date"):query_evidence(path=p,start_date=date(2024,2,1),end_date=date(2024,1,1))
def test_multi_evidence_rule_rejects_incompatible_metric_pair():
 r=adapt_operational_evidence(pd.concat([op("fintech_mau_yoy_growth","mau"),op("unique_active_buyers_yoy_growth","buyers")],ignore_index=True))
 with pytest.raises(ValueError,match="No explicit multi-evidence rule"):interpret_evidence(r,multi_evidence_groups=[["mau","buyers"]])
def test_operational_observation_keeps_observation_id_and_links_fact_id():
 f=pd.DataFrame([dict(observation_id="obs-1",evidence_id="fact-1",evidence_stage="OBSERVATION",evidence_type="meli_plus",
 business_domain="Ecosystem",reference_period="2024-03-31",observation_text="Subscribers grew.",source_statement="Subscribers grew.",
 source_url="https://sec.example",claim_kind="growth")])
 r=adapt_operational_evidence(f).iloc[0]
 assert r.evidence_id=="obs-1" and r.source_evidence_ids=='["fact-1"]' and r.evidence_type=="OBSERVATION"
