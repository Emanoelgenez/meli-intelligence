"""Read-only dataset access routed through existing query APIs when available."""
from __future__ import annotations

import importlib
from pathlib import Path

import duckdb
import pandas as pd

from meli_intelligence.ui.catalog import DatasetSpec, get_dataset_spec
from meli_intelligence.ui.filters import FilterState, apply_filters
from meli_intelligence.ui.public_demo import resolve_dataset_path


def dataset_exists(dataset_id: str, *, path: str | Path | None = None) -> bool:
    spec = get_dataset_spec(dataset_id)
    try:
        return resolve_dataset_path(dataset_id, spec.default_path, path).is_file()
    except (FileNotFoundError, PermissionError, ValueError):
        return False


def _read_parquet(path: Path) -> pd.DataFrame:
    connection = duckdb.connect(database=":memory:")
    try:
        return connection.execute("SELECT * FROM read_parquet(?)", [str(path)]).df()
    finally:
        connection.close()


def _query_existing(spec: DatasetSpec, path: Path, filters: FilterState) -> pd.DataFrame:
    if not spec.query_module or not spec.query_function or not spec.query_path_keyword:
        return _read_parquet(path)
    try:
        module = importlib.import_module(spec.query_module)
        query = getattr(module, spec.query_function)
    except (ImportError, AttributeError):
        return _read_parquet(path)
    kwargs = {spec.query_path_keyword: path}
    if spec.dataset_id in {"macro_indicators", "macro_analytics", "macro_evidence"}:
        kwargs.update(start_date=filters.start_date, end_date=filters.end_date)
    elif spec.dataset_id in {"evidence_registry", "interpretations", "pestel", "swot", "product_evidence"}:
        kwargs.update(start_date=filters.start_date, end_date=filters.end_date)
        if filters.business_domain is not None:
            kwargs["business_domain"] = filters.business_domain
    return query(**kwargs)


def load_dataset(
    dataset_id: str,
    *,
    path: str | Path | None = None,
    filters: FilterState | None = None,
) -> pd.DataFrame:
    """Load a read-only snapshot; a missing dataset raises, never fabricates rows."""
    state = (filters or FilterState()).validate()
    spec = get_dataset_spec(dataset_id)
    source = resolve_dataset_path(dataset_id, spec.default_path, path)
    if not source.is_file():
        raise FileNotFoundError(f"Dataset {dataset_id!r} is missing: {source}")
    frame = _query_existing(spec, source, state)
    return apply_filters(frame, state)
