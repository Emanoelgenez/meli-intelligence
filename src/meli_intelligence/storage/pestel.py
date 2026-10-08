"""Atomic, replay-safe Parquet Gold storage for PESTEL classifications."""
from __future__ import annotations
import json,os,tempfile
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from meli_intelligence.config.settings import GOLD_DIR
from meli_intelligence.strategy.pestel import PESTEL_COLUMNS,validate_pestel

DEFAULT_PESTEL_PATH=GOLD_DIR/"strategy"/"pestel.parquet"
PESTEL_SCHEMA_VERSION="1"
_SCHEMA=pa.schema([pa.field(c,pa.date32() if c in {"reference_date","period_start","period_end"} else pa.bool_() if c=="is_interpretation" else pa.string(),nullable=c not in {"pestel_id","pestel_dimension","business_domain","claim","classification_rationale","source_evidence_ids","source_evidence_types","source_metric_ids","source","is_interpretation","methodology_version","definition_context"}) for c in PESTEL_COLUMNS],metadata={b"schema_version":b"1",b"dataset":b"pestel"})
def _fingerprint(row):
 return json.dumps({k:(v.isoformat() if hasattr(v,"isoformat") else None if pd.isna(v) else v.item() if hasattr(v,"item") else v) for k,v in row.items()},sort_keys=True,default=str,ensure_ascii=False)
def _merge(old,new):
 a=validate_pestel(old) if not old.empty else pd.DataFrame(columns=PESTEL_COLUMNS);b=validate_pestel(new)
 if a.pestel_id.duplicated(keep=False).any():raise ValueError("Stored PESTEL IDs are not unique.")
 om={str(r.pestel_id):_fingerprint(r.to_dict()) for _,r in a.iterrows()};nm={}
 for _,r in b.iterrows():
  k=str(r.pestel_id);v=_fingerprint(r.to_dict())
  if k in nm and nm[k]!=v:raise ValueError(f"Incoming PESTEL identity conflict for pestel_id={k!r}.")
  nm[k]=v
 for k in set(om)&set(nm):
  if om[k]!=nm[k]:raise ValueError(f"PESTEL identity conflict for pestel_id={k!r}.")
 fresh=b.loc[~b.pestel_id.astype(str).isin(om)]
 return validate_pestel(pd.concat([a,fresh],ignore_index=True))
def write_pestel(frame,path=DEFAULT_PESTEL_PATH):
 result=validate_pestel(frame);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 old=pq.read_table(path).to_pandas() if path.exists() else pd.DataFrame(columns=PESTEL_COLUMNS)
 merged=_merge(old,result);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=f".{path.name}.",suffix=".tmp");os.close(fd)
 try:
  pq.write_table(pa.Table.from_pandas(merged[PESTEL_COLUMNS],schema=_SCHEMA,preserve_index=False,safe=True),tmp,compression="zstd")
  os.replace(tmp,path)
 except Exception:
  Path(tmp).unlink(missing_ok=True);raise
 return path
