"""Common, auditable Evidence schema and normalization helpers."""
from __future__ import annotations
import json
import pandas as pd

EVIDENCE_TYPES = frozenset({"FACT", "OBSERVATION", "INTERPRETATION"})
EVIDENCE_COLUMNS = [
    "evidence_id", "evidence_type", "business_domain", "entity", "metric_id",
    "reference_date", "period_start", "period_end", "period_type", "period_label",
    "value", "unit", "frequency", "claim", "claim_kind", "source",
    "source_url", "filing_date", "accession_number", "source_bronze_file", "source_content_sha256", "source_metric_id", "source_evidence_ids", "is_interpretation",
    "methodology_version", "definition_context",
]

def encode_source_ids(value):
    if value is None or (isinstance(value, float) and pd.isna(value)): ids=[]
    elif isinstance(value, str):
        try: ids=json.loads(value)
        except json.JSONDecodeError: ids=[value] if value else []
    else: ids=[str(x) for x in value]
    return json.dumps(sorted(set(map(str, ids))), separators=(",", ":"), ensure_ascii=False)

def source_ids(row):
    value=row["source_evidence_ids"]
    return json.loads(value) if isinstance(value,str) else list(value)

def normalize_evidence(frame):
    missing=set(EVIDENCE_COLUMNS)-set(frame.columns)
    if missing: raise ValueError(f"Evidence missing columns: {sorted(missing)}")
    result=frame[EVIDENCE_COLUMNS].copy()
    if result.empty: return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    if result.evidence_id.isna().any() or result.evidence_id.astype(str).str.strip().eq("").any():
        raise ValueError("Evidence IDs must be non-empty.")
    if result.evidence_id.duplicated(keep=False).any(): raise ValueError("Evidence IDs must be unique.")
    invalid=set(result.evidence_type.astype(str))-EVIDENCE_TYPES
    if invalid: raise ValueError(f"Unsupported evidence types: {sorted(invalid)}")
    required=["business_domain","claim","claim_kind","source","is_interpretation","methodology_version","definition_context"]
    if result[required].isna().any().any(): raise ValueError("Evidence required fields cannot be null.")
    for col in ("business_domain","claim","source"):
        if result[col].astype(str).str.strip().eq("").any(): raise ValueError(f"Evidence {col} cannot be empty.")
    result["source_evidence_ids"]=result.source_evidence_ids.map(encode_source_ids)
    for col in ("reference_date","period_start","period_end","filing_date"):
        result[col]=pd.to_datetime(result[col],errors="raise").dt.date
    result["is_interpretation"]=result.evidence_type.eq("INTERPRETATION")
    orphan=result.loc[result.evidence_type.eq("INTERPRETATION"),"source_evidence_ids"].map(lambda s:not json.loads(s))
    if orphan.any(): raise ValueError("Interpretations must reference at least one source evidence ID.")
    return result.sort_values(["reference_date","business_domain","metric_id","evidence_id"],na_position="last",kind="mergesort").reset_index(drop=True)
