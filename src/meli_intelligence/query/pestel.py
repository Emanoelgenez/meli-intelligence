"""DuckDB read helpers for PESTEL classifications."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
import duckdb
import pandas as pd
from meli_intelligence.storage.pestel import DEFAULT_PESTEL_PATH
from meli_intelligence.strategy.pestel import PESTEL_DIMENSIONS

def query_pestel(*,path:Path=DEFAULT_PESTEL_PATH,pestel_dimension:str|None=None,
 business_domain:str|None=None,metric_id:str|None=None,start_date:date|None=None,
 end_date:date|None=None,source_evidence_id:str|None=None)->pd.DataFrame:
 if pestel_dimension is not None and pestel_dimension not in PESTEL_DIMENSIONS:raise ValueError(f"Invalid PESTEL dimension: {pestel_dimension}")
 path=Path(path)
 if not path.exists():raise FileNotFoundError(f"PESTEL Parquet not found: {path}")
 if start_date and end_date and start_date>end_date:raise ValueError("start_date must be on or before end_date.")
 cond=[];params=[str(path)]
 for col,val in (("pestel_dimension",pestel_dimension),("business_domain",business_domain)):
  if val is not None:cond.append(f"{col} = ?");params.append(val)
 if start_date is not None:cond.append("reference_date >= ?");params.append(start_date)
 if end_date is not None:cond.append("reference_date <= ?");params.append(end_date)
 where=" WHERE "+" AND ".join(cond) if cond else ""
 con=duckdb.connect(":memory:")
 try:out=con.execute(f"SELECT * FROM read_parquet(?) {where} ORDER BY reference_date,pestel_dimension,business_domain,pestel_id",params).df()
 finally:con.close()
 if metric_id is not None:out=out.loc[out.source_metric_ids.map(lambda s:metric_id in json.loads(s))]
 if source_evidence_id is not None:out=out.loc[out.source_evidence_ids.map(lambda s:source_evidence_id in json.loads(s))]
 return out.reset_index(drop=True)
