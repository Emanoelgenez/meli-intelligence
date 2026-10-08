"""Atomic, replay-safe Parquet storage for common Evidence Gold datasets."""
from __future__ import annotations
import json,os,tempfile
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from meli_intelligence.config.settings import GOLD_DIR
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS,normalize_evidence

EVIDENCE_SCHEMA_VERSION="1"
DEFAULT_EVIDENCE_REGISTRY_PATH=GOLD_DIR/"evidence"/"evidence_registry.parquet"
DEFAULT_INTERPRETATIONS_PATH=GOLD_DIR/"evidence"/"interpretations.parquet"
_SCHEMA=pa.schema([pa.field(c,pa.date32() if c in {"reference_date","period_start","period_end","filing_date"} else pa.float64() if c=="value" else pa.bool_() if c=="is_interpretation" else pa.string(),nullable=c not in {"evidence_id","evidence_type","business_domain","claim","claim_kind","source","source_evidence_ids","is_interpretation","methodology_version","definition_context"}) for c in EVIDENCE_COLUMNS],metadata={b"schema_version":b"1"})
def _fingerprint(row):
 return json.dumps({k:(v.isoformat() if hasattr(v,"isoformat") else None if pd.isna(v) else v.item() if hasattr(v,"item") else v) for k,v in row.items()},sort_keys=True,default=str,ensure_ascii=False)
def _merge(old,new):
 a=normalize_evidence(old) if not old.empty else pd.DataFrame(columns=EVIDENCE_COLUMNS);b=normalize_evidence(new)
 if a.evidence_id.duplicated(keep=False).any():raise ValueError("Stored Evidence IDs are not unique.")
 om={str(r.evidence_id):_fingerprint(r.to_dict()) for _,r in a.iterrows()};nm={}
 for _,r in b.iterrows():
  k=str(r.evidence_id);v=_fingerprint(r.to_dict())
  if k in nm and nm[k]!=v:raise ValueError(f"Incoming Evidence identity conflict for evidence_id={k!r}.")
  nm[k]=v
 for k in set(om)&set(nm):
  if om[k]!=nm[k]:raise ValueError(f"Evidence identity conflict for evidence_id={k!r}.")
 fresh=b.loc[~b.evidence_id.astype(str).isin(om)]
 return normalize_evidence(pd.concat([a,fresh],ignore_index=True))
def _write(frame,path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=f".{path.name}.",suffix=".tmp");os.close(fd)
 try:
  pq.write_table(pa.Table.from_pandas(frame[EVIDENCE_COLUMNS],schema=_SCHEMA,preserve_index=False,safe=True),tmp,compression="zstd")
  os.replace(tmp,path)
 except Exception:
  Path(tmp).unlink(missing_ok=True);raise
 return path
def _write_dataset(frame,path,interpretations):
 f=normalize_evidence(frame)
 if interpretations and not f.empty and not f.evidence_type.eq("INTERPRETATION").all():raise ValueError("Interpretations dataset accepts INTERPRETATION rows only.")
 path=Path(path);old=pq.read_table(path).to_pandas() if path.exists() else pd.DataFrame(columns=EVIDENCE_COLUMNS)
 return _write(_merge(old,f),path)
def write_evidence_registry(frame,path=DEFAULT_EVIDENCE_REGISTRY_PATH):return _write_dataset(frame,path,False)
def write_interpretations(frame,path=DEFAULT_INTERPRETATIONS_PATH):return _write_dataset(frame,path,True)
