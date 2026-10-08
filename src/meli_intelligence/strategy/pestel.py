"""Deterministic PESTEL classification of existing common Evidence records."""
from __future__ import annotations
import hashlib,json
import pandas as pd
from meli_intelligence.evidence.model import normalize_evidence,source_ids

METHODOLOGY_VERSION="1"
PESTEL_DIMENSIONS=frozenset({"POLITICAL","ECONOMIC","SOCIAL","TECHNOLOGICAL","ENVIRONMENTAL","LEGAL"})
PESTEL_COLUMNS=[
 "pestel_id","pestel_dimension","business_domain","reference_date","period_start","period_end","period_type","entity",
 "claim","classification_rationale","source_evidence_ids","source_evidence_types","source_metric_ids","source",
 "is_interpretation","methodology_version","definition_context"
]
ECONOMIC_METRICS=frozenset({
 "selic_target_annual","selic_effective_annual_252","selic_target_change_pp",
 "ipca_monthly_change","ipca_12m_change","ipca_12m_change_pp","usd_brl_sell_rate","usd_brl_month_end","usd_brl_monthly_change_pct",
 "household_free_credit_balance","household_free_credit_balance_yoy_growth",
 "household_free_credit_npl_90d_rate","household_free_credit_npl_90d_yoy_change_pp",
 "ibc_br_activity_sa_index","ibc_br_activity_mom_change_pct","unemployment_rate_rolling_3m",
 "unemployment_rate_change_pp","retail_sales_volume_mom_sa","pix_transactions_count_monthly",
 "pix_transactions_value_monthly","pix_transactions_count_yoy_growth","pix_transactions_value_yoy_growth",
})
SOCIAL_METRICS={
 "fintech_mau":{"Fintech"},"fintech_mau_yoy_growth":{"Fintech"},
 "unique_active_buyers":{"Commerce"},"unique_active_buyers_yoy_growth":{"Commerce"},
}
TECH_ADOPTION_CLAIMS=frozenset({"technology_adoption","digital_payment_adoption","digital_infrastructure"})
STRUCTURED_DIMENSIONS={
 "POLITICAL":frozenset({"public_policy","government_decision"}),
 "LEGAL":frozenset({"regulatory_requirement","compliance_obligation"}),
 "ENVIRONMENTAL":frozenset({"environmental_measurement","environmental_impact"}),
}
RATIONALES={
 "ECONOMIC":"Classified as ECONOMIC because the source metric is an official macroeconomic or payment activity indicator.",
 "SOCIAL":"Classified as SOCIAL because the source metric reports an explicitly identified user base or buyer activity.",
 "TECHNOLOGICAL":"Classified as TECHNOLOGICAL because the source evidence explicitly tags technology or digital infrastructure adoption.",
 "POLITICAL":"Classified as POLITICAL because the source evidence explicitly identifies a public policy or government decision.",
 "LEGAL":"Classified as LEGAL because the source evidence explicitly identifies a regulatory or compliance obligation.",
 "ENVIRONMENTAL":"Classified as ENVIRONMENTAL because the source evidence explicitly identifies an environmental measure.",
}
_FORBIDDEN=(
 "recommendation","opportunity","threat","strength","weakness","should build","must build","feature","solution",
 "caused","causes","because of","led to","explains","proves","causal",
 "recomendação","oportunidade","ameaça","força","fraqueza","deveria construir","solução","causou","causa","explica","prova",
)

def _json_ids(value):
 if value is None or (isinstance(value,float) and pd.isna(value)):return []
 if isinstance(value,str):
  try:
   decoded=json.loads(value)
   return [str(x) for x in decoded]
  except json.JSONDecodeError:return [value] if value else []
 return [str(x) for x in value]

def classify_evidence(row):
 """Return one allowlisted dimension and rationale, or None when unsupported."""
 metric="" if row.get("metric_id") is None or pd.isna(row.get("metric_id")) else str(row.get("metric_id"))
 domain=str(row.get("business_domain") or "")
 kind=str(row.get("claim_kind") or "")
 context=str(row.get("definition_context") or "")
 if metric in {"pix_transactions_count_monthly","pix_transactions_count_yoy_growth"} and kind in TECH_ADOPTION_CLAIMS and "technology_adoption" in context:
  return "TECHNOLOGICAL",RATIONALES["TECHNOLOGICAL"]
 if metric in ECONOMIC_METRICS and domain=="Macro":
  return "ECONOMIC",RATIONALES["ECONOMIC"]
 if metric in SOCIAL_METRICS and domain in SOCIAL_METRICS[metric] and kind in {"level","growth","increase","yoy_growth","yoy_decline","other"}:
  return "SOCIAL",RATIONALES["SOCIAL"]
 if kind in STRUCTURED_DIMENSIONS["POLITICAL"] and metric and row.get("source"):
  return "POLITICAL",RATIONALES["POLITICAL"]
 if kind in STRUCTURED_DIMENSIONS["LEGAL"] and metric and row.get("source"):
  return "LEGAL",RATIONALES["LEGAL"]
 if kind in STRUCTURED_DIMENSIONS["ENVIRONMENTAL"] and metric and row.get("source"):
  return "ENVIRONMENTAL",RATIONALES["ENVIRONMENTAL"]
 return None

def _pestel_id(dimension,claim,ids,reference_date):
 payload={"pestel_dimension":dimension,"claim":claim,"source_evidence_ids":sorted(ids),
          "reference_date":None if pd.isna(reference_date) else pd.Timestamp(reference_date).date().isoformat()}
 raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"))
 return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def validate_pestel(frame):
 missing=set(PESTEL_COLUMNS)-set(frame.columns)
 if missing:raise ValueError(f"PESTEL missing columns: {sorted(missing)}")
 f=frame[PESTEL_COLUMNS].copy()
 invalid=set(f.pestel_dimension.dropna().astype(str))-PESTEL_DIMENSIONS
 if invalid:raise ValueError(f"Invalid PESTEL dimensions: {sorted(invalid)}")
 if f.pestel_id.isna().any() or f.pestel_id.duplicated(keep=False).any():raise ValueError("PESTEL IDs must be non-empty and unique.")
 required=["pestel_dimension","business_domain","claim","classification_rationale","source_evidence_ids","source_evidence_types","source_metric_ids","source","is_interpretation","methodology_version","definition_context"]
 if f[required].isna().any().any():raise ValueError("PESTEL required fields cannot be null.")
 for i,row in f.iterrows():
  ids=_json_ids(row.source_evidence_ids)
  types=_json_ids(row.source_evidence_types)
  if not ids or len(ids)!=len(types):raise ValueError("PESTEL lineage IDs and evidence types must be non-empty and aligned.")
  if any(term in str(row.claim).casefold() for term in _FORBIDDEN):raise ValueError("PESTEL claim contains causal or prescriptive language.")
  if any(term in str(row.classification_rationale).casefold() for term in _FORBIDDEN):raise ValueError("PESTEL rationale contains prohibited strategy language.")
 f["reference_date"]=pd.to_datetime(f.reference_date,errors="raise").dt.date
 f["period_start"]=pd.to_datetime(f.period_start,errors="raise").dt.date
 f["period_end"]=pd.to_datetime(f.period_end,errors="raise").dt.date
 return f.sort_values(["reference_date","pestel_dimension","business_domain","pestel_id"],na_position="last",kind="mergesort").reset_index(drop=True)

def validate_pestel_lineage(pestel,evidence_registry):
 known={str(x) for x in evidence_registry.evidence_id}
 types=dict(zip(evidence_registry.evidence_id.astype(str),evidence_registry.evidence_type.astype(str)))
 for _,row in pestel.iterrows():
  ids=_json_ids(row.source_evidence_ids);unknown=set(ids)-known
  if unknown:raise ValueError(f"Unknown source_evidence_id values: {sorted(unknown)}")
  expected=[types[x] for x in ids]
  if expected!=_json_ids(row.source_evidence_types):raise ValueError("PESTEL source evidence types do not match the Evidence Registry.")
 return None

def build_pestel(evidence_registry):
 """Classify supported registry records once each; unsupported records are omitted."""
 evidence=normalize_evidence(evidence_registry)
 known=set(evidence.evidence_id.astype(str))
 type_by_id=dict(zip(evidence.evidence_id.astype(str),evidence.evidence_type.astype(str)))
 row_by_id={str(r.evidence_id):r for _,r in evidence.iterrows()}
 rows=[]
 for _,row in evidence.iterrows():
  classified=classify_evidence(row)
  if classified is None:continue
  dimension,rationale=classified
  upstream=_json_ids(row.source_evidence_ids)
  unknown=set(upstream)-known
  if unknown:raise ValueError(f"Unknown source_evidence_id values: {sorted(unknown)}")
  ids=sorted(set([str(row.evidence_id),*upstream]))
  types=[type_by_id[x] for x in ids]
  linked_rows=[row_by_id[x] for x in ids]
  metric_ids=sorted({metric for linked in linked_rows if pd.notna(linked.source_metric_id) for metric in str(linked.source_metric_id).split(";") if metric})
  sources=sorted({str(linked.source) for linked in linked_rows if pd.notna(linked.source)})
  claim=str(row.claim)
  if any(term in claim.casefold() for term in _FORBIDDEN):raise ValueError("Evidence claim contains causal or prescriptive language.")
  rows.append({
   "pestel_id":_pestel_id(dimension,claim,ids,row.reference_date),"pestel_dimension":dimension,
   "business_domain":row.business_domain,"reference_date":row.reference_date,"period_start":row.period_start,
   "period_end":row.period_end,"period_type":row.period_type,"entity":row.entity,"claim":claim,
   "classification_rationale":rationale,"source_evidence_ids":json.dumps(ids,separators=(",",":"),ensure_ascii=False),
   "source_evidence_types":json.dumps(types,separators=(",",":"),ensure_ascii=False),
   "source_metric_ids":json.dumps(metric_ids,separators=(",",":"),ensure_ascii=False),
   "source":";".join(sources),"is_interpretation":bool(row.is_interpretation),
   "methodology_version":METHODOLOGY_VERSION,"definition_context":row.definition_context,
  })
 result=pd.DataFrame(rows,columns=PESTEL_COLUMNS)
 if result.empty:return result
 result=validate_pestel(result)
 validate_pestel_lineage(result,evidence)
 return result
