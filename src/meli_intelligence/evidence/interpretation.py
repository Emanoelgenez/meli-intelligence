"""Deterministic, auditable, non-causal interpretation rules."""
from __future__ import annotations
import hashlib,json,re
import pandas as pd
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS,normalize_evidence,source_ids

METHODOLOGY_VERSION="1"
_FORBIDDEN=re.compile(r"\b(caused|causes|because of|led to|drives?|explains?|proves?|recommend(?:ation)?|should build|must build|feature|solution|causar|causou|por causa de|levou a|explica|prova|recomenda(?:ção)?|deveria construir|deve construir|funcionalidade|solução|oportunidade|ameaça)\b",re.I)
_RULES={
"net_revenues_financial_income_yoy_growth":("positive_value","Revenue increased versus the comparable period, indicating expansion in reported revenue.","reported_revenue_expansion"),
"revenue_yoy_growth":("positive_value","Revenue increased versus the comparable period, indicating expansion in reported revenue.","reported_revenue_expansion"),
"gmv_yoy_growth":("positive_value","GMV increased versus the comparable period, indicating expansion in reported commerce volume.","reported_gmv_expansion"),
"fintech_mau_yoy_growth":("positive_value","Fintech MAU increased versus the comparable period, indicating a larger reported active fintech user base.","reported_fintech_user_base_expansion"),
"pix_transactions_count_yoy_growth":("growth_claim","Pix transaction volume increased versus the same month of the prior year, indicating greater reported Pix usage.","reported_pix_usage_increase"),
"selic_target_change_pp":("decline_claim","The Selic target declined versus the previous observation.","reported_selic_decline"),
}
def _hash(p):
    return hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str).encode()).hexdigest()
def _eligible(rule,row):
    value=row.get("value")
    if rule=="positive_value": return value is not None and not pd.isna(value) and float(value)>0
    if rule=="growth_claim": return row.claim_kind in {"yoy_growth","increase"}
    if rule=="decline_claim": return row.claim_kind=="decrease"
    return False
def _record(sources,claim,metric,kind):
    ids=sorted(str(x.evidence_id) for x in sources); r=sources[0]
    if _FORBIDDEN.search(claim): raise ValueError("Interpretation uses causal or prescriptive language.")
    payload={"type":"INTERPRETATION","domain":r.business_domain,"metric":metric,"date":r.reference_date,"claim":claim,"sources":ids}
    return dict(evidence_id=_hash(payload),evidence_type="INTERPRETATION",business_domain=r.business_domain,entity=r.entity,
      metric_id=metric,reference_date=r.reference_date,period_start=r.period_start,period_end=r.period_end,
      period_type=r.period_type,period_label=r.period_label,value=(r.value if len(sources)==1 else None),unit=(r.unit if len(sources)==1 else None),frequency=r.frequency,
      claim=claim,claim_kind=kind,source="deterministic_rule_based_interpretation",
      source_metric_id=";".join(sorted(set(str(x.source_metric_id) for x in sources if pd.notna(x.source_metric_id)))),
      source_evidence_ids=ids,is_interpretation=True,methodology_version=METHODOLOGY_VERSION,
      definition_context="rule_based;non_causal;source_claim_preserved")
def _compatible(rows):
    if len(rows)!=2 or any(r.evidence_type!="OBSERVATION" for r in rows): raise ValueError("Multi-evidence interpretation requires two source OBSERVATION records.")
    a,b=rows
    if a.reference_date!=b.reference_date: raise ValueError("Evidence periods are incompatible.")
    for key in ("period_type","period_label"):
        vals={str(r[key]) for r in rows if pd.notna(r[key])}
        if len(vals)>1: raise ValueError(f"Evidence periods are incompatible: {key}.")
    if a.definition_context!=b.definition_context: raise ValueError("Evidence definitions are incompatible.")
    if a.business_domain!=b.business_domain: raise ValueError("Evidence domains are incompatible.")
    if {a.metric_id,b.metric_id}!={"fintech_mau_yoy_growth","tpv_yoy_growth"}: raise ValueError("No explicit multi-evidence rule for this metric combination.")
    if any(not _eligible("positive_value",r) for r in rows): raise ValueError("Multi-evidence growth requires positive values.")
def interpret_evidence(evidence,multi_evidence_groups=None):
    """Build allowlisted single and explicitly requested multi-source interpretations."""
    reg=normalize_evidence(evidence); known=set(reg.evidence_id.astype(str)); idx={str(r.evidence_id):r for _,r in reg.iterrows()}; rows=[]
    for _,r in reg.iterrows():
        if r.evidence_type!="OBSERVATION": continue
        spec=_RULES.get(str(r.metric_id))
        if spec and _eligible(spec[0],r): rows.append(_record([r],spec[1],str(r.metric_id),spec[2]))
    for group in multi_evidence_groups or []:
        missing=set(group)-known
        if missing: raise ValueError(f"Unknown source_evidence_id values: {sorted(missing)}")
        sources=[idx[x] for x in group]; _compatible(sources)
        rows.append(_record(sources,"Fintech active users and TPV both increased in the comparable periods represented by the selected evidence.","fintech_mau_and_tpv_yoy_growth","joint_increase"))
    result=pd.DataFrame(rows,columns=EVIDENCE_COLUMNS)
    if result.empty: return result
    if result.evidence_id.duplicated().any(): raise ValueError("Duplicate interpretation ID.")
    return normalize_evidence(result)
def validate_interpretation_lineage(interpretations,evidence_registry):
    known=set(evidence_registry.evidence_id.astype(str))
    for _,r in interpretations.iterrows():
        missing=set(source_ids(r))-known
        if missing: raise ValueError(f"Unknown source_evidence_id values: {sorted(missing)}")
