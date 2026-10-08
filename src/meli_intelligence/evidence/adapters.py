"""Adapters from existing operational, macro, and financial datasets."""
from __future__ import annotations
import hashlib, json
import pandas as pd
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence

METHODOLOGY_VERSION="1"

def _id(data):
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(raw.encode()).hexdigest()

def _date(x):
    return None if x is None or pd.isna(x) else pd.to_datetime(x).date()

def _row(**x):
    return dict(evidence_id=str(x["evidence_id"]),evidence_type=x["evidence_type"],
        business_domain=str(x["business_domain"]),entity=x.get("entity"),metric_id=x.get("metric_id"),
        reference_date=_date(x.get("reference_date")),period_start=_date(x.get("period_start")),
        period_end=_date(x.get("period_end")),period_type=x.get("period_type"),period_label=x.get("period_label"),
        value=x.get("value"),unit=x.get("unit"),frequency=x.get("frequency"),claim=str(x["claim"]),
        claim_kind=str(x.get("claim_kind") or "other"),source=str(x["source"]),
        source_url=x.get("source_url"),filing_date=_date(x.get("filing_date")),accession_number=x.get("accession_number"),source_bronze_file=x.get("source_bronze_file"),source_content_sha256=x.get("source_content_sha256"),source_metric_id=x.get("source_metric_id"),source_evidence_ids=x.get("source_evidence_ids",[]),
        is_interpretation=x["evidence_type"]=="INTERPRETATION",methodology_version=METHODOLOGY_VERSION,
        definition_context=str(x.get("definition_context") or "source_definition_preserved"))

def _out(rows): return normalize_evidence(pd.DataFrame(rows,columns=EVIDENCE_COLUMNS))

def adapt_operational_evidence(frame):
    """Preserve source IDs and statements from operational evidence facts/observations."""
    rows=[]
    for r in frame.to_dict("records"):
        if "statement" in r or "observation_text" in r:
            typ="OBSERVATION" if str(r.get("evidence_stage","")).upper()=="OBSERVATION" else "FACT"
            eid=r.get("observation_id") or r.get("evidence_id")
            rows.append(_row(evidence_id=eid,evidence_type=typ,business_domain=r.get("business_domain",r.get("evidence_type","Operational")),
                entity=r.get("entity_name"),metric_id=r.get("metric_id"),reference_date=r.get("reference_period",r.get("reference_date")),
                claim=r.get("statement",r.get("observation_text",r.get("source_statement",""))),claim_kind=r.get("claim_kind",r.get("evidence_type","other")),
                source=r.get("source") or r.get("source_url") or "SEC operational filing",
                source_metric_id=r.get("source_metric_id",r.get("metric_id")),
                source_evidence_ids=[r["evidence_id"]] if r.get("observation_id") else [],
                period_start=r.get("period_start"),period_end=r.get("period_end"),period_type=r.get("period_type"),
                period_label=r.get("period_label"),definition_context=r.get("definition_context","source_statement_preserved"),source_url=r.get("source_url"),filing_date=r.get("filing_date"),accession_number=r.get("accession_number"),source_bronze_file=r.get("source_bronze_file"),source_content_sha256=r.get("source_content_sha256")))
        elif "claim" in r and "metric_id" in r:
            eid=r.get("evidence_id") or _id({"metric":r["metric_id"],"date":r.get("reference_date"),"claim":r["claim"]})
            rows.append(_row(evidence_id=eid,evidence_type=str(r.get("evidence_type","OBSERVATION")).upper(),
                business_domain=r.get("business_domain","Operational"),entity=r.get("entity"),metric_id=r["metric_id"],
                reference_date=r.get("reference_date"),claim=r["claim"],claim_kind=r.get("claim_kind","other"),
                source=r.get("source","SEC operational analytics"),source_metric_id=r.get("source_metric_id",r["metric_id"]),
                source_evidence_ids=r.get("source_evidence_ids",[]),value=r.get("value"),unit=r.get("unit"),
                frequency=r.get("frequency"),period_start=r.get("period_start"),period_end=r.get("period_end"),
                period_type=r.get("period_type"),period_label=r.get("period_label"),
                definition_context=r.get("definition_context","operational_definition_preserved"),source_url=r.get("source_url"),filing_date=r.get("filing_date"),accession_number=r.get("accession_number"),source_bronze_file=r.get("source_bronze_file"),source_content_sha256=r.get("source_content_sha256")))
        else: raise ValueError("Operational evidence requires statement or common claim fields.")
    return _out(rows)

def adapt_macro_evidence(frame):
    """Preserve Sprint 3G OBSERVATION identity; never relabel it FACT."""
    required={"evidence_id","evidence_type","business_domain","metric_id","reference_date","claim","source"}
    if required-set(frame.columns): raise ValueError(f"Macro evidence missing columns: {sorted(required-set(frame.columns))}")
    rows=[]
    for r in frame.to_dict("records"):
        typ=str(r["evidence_type"]).upper()
        if typ!="OBSERVATION": raise ValueError("Macro adapter accepts OBSERVATION rows only.")
        rows.append(_row(evidence_id=r["evidence_id"],evidence_type=typ,business_domain=r["business_domain"],
            entity="Brazil",metric_id=r["metric_id"],reference_date=r["reference_date"],claim=r["claim"],
            claim_kind=r.get("claim_kind","level"),source=r["source"],source_url=r.get("source_url"),filing_date=r.get("filing_date"),accession_number=r.get("accession_number"),source_bronze_file=r.get("source_bronze_file"),source_content_sha256=r.get("source_content_sha256"),source_metric_id=r.get("source_metric_id",r["metric_id"]),
            source_evidence_ids=r.get("source_evidence_ids",[]),value=r.get("value"),unit=r.get("unit"),
            frequency=r.get("frequency"),period_start=r.get("period_start"),period_end=r.get("period_end"),
            period_type=r.get("period_type"),period_label=r.get("period_label"),
            definition_context=r.get("definition_context","reported_macro_observation")))
    return _out(rows)

def adapt_financial_evidence(frame):
    """Adapt existing SEC facts or financial analytics without deriving metrics."""
    rows=[]
    for r in frame.to_dict("records"):
        metric=str(r.get("metric_id","")); ref=r.get("period_end",r.get("reference_date"))
        if not metric or ref is None or pd.isna(ref): raise ValueError("Financial evidence requires metric_id and period_end/reference_date.")
        source=r.get("source") or r.get("source_url") or "SEC financial analytics"; value=r.get("value"); unit=r.get("unit")
        claim=r.get("claim",r.get("statement"))
        typ=str(r.get("evidence_type","OBSERVATION")).upper()
        if claim is None:
            if value is None or pd.isna(value): raise ValueError("Financial analytics row has no value.")
            period=str(r.get("period_label") or pd.to_datetime(ref).date().isoformat())
            claim=f"Financial metric {metric} was {float(value):.15g} {unit or ''} for {period}."
        eid=r.get("evidence_id") or _id({"type":typ,"metric":metric,"date":ref,"claim":claim,"source":source})
        kind=r.get("claim_kind","level")
        if metric.endswith("_yoy_growth") and value is not None and not pd.isna(value):
            kind="yoy_growth" if float(value)>0 else "yoy_decline" if float(value)<0 else "unchanged"
        rows.append(_row(evidence_id=eid,evidence_type=typ,business_domain=r.get("business_domain","Financial"),
            entity=r.get("entity_name",r.get("entity")),metric_id=metric,reference_date=ref,claim=claim,claim_kind=kind,
            source=source,source_url=r.get("source_url"),filing_date=r.get("filing_date"),accession_number=r.get("accession_number"),source_bronze_file=r.get("source_bronze_file"),source_content_sha256=r.get("source_content_sha256"),source_metric_id=r.get("source_metric_id",r.get("source_metrics",metric)),
            source_evidence_ids=r.get("source_evidence_ids",[]),value=value,unit=unit,frequency=r.get("frequency"),
            period_start=r.get("period_start"),period_end=r.get("period_end",ref),period_type=r.get("period_type"),
            period_label=r.get("period_label"),definition_context=r.get("definition_context",r.get("formula","reported_financial_metric"))))
    return _out(rows)

def build_evidence_registry(*,financial=None,operational=None,macro=None):
    """Combine source-specific Evidence into one deterministically ordered registry."""
    datasets=[]
    if financial is not None: datasets.append(adapt_financial_evidence(financial))
    if operational is not None: datasets.append(adapt_operational_evidence(operational))
    if macro is not None: datasets.append(adapt_macro_evidence(macro))
    if not datasets: return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    combined=pd.concat(datasets,ignore_index=True)
    if combined.evidence_id.duplicated(keep=False).any(): raise ValueError("Evidence ID collision across source datasets.")
    return normalize_evidence(combined)
