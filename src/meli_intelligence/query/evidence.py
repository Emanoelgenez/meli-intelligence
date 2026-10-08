"""DuckDB read layer for common Evidence Parquet."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
import duckdb
import pandas as pd
from meli_intelligence.storage.evidence import DEFAULT_EVIDENCE_REGISTRY_PATH,DEFAULT_INTERPRETATIONS_PATH

def query_evidence(*,path:Path=DEFAULT_EVIDENCE_REGISTRY_PATH,evidence_type:str|None=None,business_domain:str|None=None,metric_id:str|None=None,start_date:date|None=None,end_date:date|None=None,source_evidence_id:str|None=None)->pd.DataFrame:
 path=Path(path)
 if not path.exists():raise FileNotFoundError(f"Evidence Parquet not found: {path}")
 if start_date and end_date and start_date>end_date:raise ValueError("start_date must be on or before end_date.")
 cond=[];params=[str(path)]
 for col,val in (("evidence_type",evidence_type),("business_domain",business_domain),("metric_id",metric_id)):
  if val is not None:cond.append(f"{col} = ?");params.append(val)
 if start_date is not None:cond.append("reference_date >= ?");params.append(start_date)
 if end_date is not None:cond.append("reference_date <= ?");params.append(end_date)
 where=" WHERE "+" AND ".join(cond) if cond else ""
 con=duckdb.connect(":memory:")
 try:out=con.execute(f"SELECT * FROM read_parquet(?) {where} ORDER BY reference_date,evidence_type,evidence_id",params).df()
 finally:con.close()
 if source_evidence_id is not None:out=out.loc[out.source_evidence_ids.map(lambda s:source_evidence_id in json.loads(s))]
 return out.reset_index(drop=True)
def query_interpretations(*,path:Path=DEFAULT_INTERPRETATIONS_PATH,**filters):return query_evidence(path=path,evidence_type="INTERPRETATION",**filters)
