"""Ingest the seasonally adjusted BCB IBC-Br series into macro Silver."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from meli_intelligence.metadata.bcb_series import get_bcb_series
from meli_intelligence.sources.bcb.sgs_client import BCBSeriesClient
from meli_intelligence.storage.bcb_bronze import (
    DEFAULT_BCB_SGS_BRONZE_DIR,
    save_bcb_sgs_bronze,
)
from meli_intelligence.storage.macro import (
    DEFAULT_MACRO_INDICATORS_PATH,
    merge_macro_indicators,
    read_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.transformations.bcb_sgs import normalize_sgs_payload


ACTIVITY_SERIES_CODES = (24364,)


def build_bcb_activity_silver(
    start_date: date,
    end_date: date,
    *,
    client: BCBSeriesClient | None = None,
    bronze_dir: Path = DEFAULT_BCB_SGS_BRONZE_DIR,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
) -> tuple[pd.DataFrame, list[tuple[Path, Path]], Path, Path]:
    """Fetch only SGS 24364 and merge its month-end observations."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    code = ACTIVITY_SERIES_CODES[0]
    series = get_bcb_series(code)
    owns_client = client is None
    resolved_client = client or BCBSeriesClient()
    bronze_paths: list[tuple[Path, Path]] = []
    frames: list[pd.DataFrame] = []
    try:
        for fetch in resolved_client.fetch_series(code, start_date, end_date):
            if fetch.series_code != code:
                raise ValueError("BCB client returned an unexpected series code.")
            bronze_paths.append(save_bcb_sgs_bronze(fetch, bronze_dir=bronze_dir))
            frames.append(normalize_sgs_payload(
                fetch.records, code, source_url=fetch.source_url,
                retrieved_at=fetch.retrieved_at,
            ))
    finally:
        if owns_client:
            resolved_client.close()
    if not frames:
        raise ValueError(f"BCB SGS returned no observations for required series {code} ({series.metric_id}).")
    incoming = pd.concat(frames, ignore_index=True)
    if incoming.empty:
        raise ValueError(f"BCB SGS returned no observations for required series {code} ({series.metric_id}).")
    if set(incoming["metric_id"]) != {"ibc_br_activity_sa_index"}:
        raise ValueError("BCB activity pipeline received an unexpected metric_id.")
    if set(incoming["source_series_id"]) != {"bcb_sgs:24364"}:
        raise ValueError("BCB activity pipeline received an unexpected source_series_id.")
    if incoming.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("BCB activity response contains duplicate economic keys.")
    output = Path(output_path)
    silver = (
        merge_macro_indicators(read_macro_indicators(output), incoming)
        if output.exists()
        else incoming.sort_values(["reference_date", "metric_id"]).reset_index(drop=True)
    )
    silver_path, metadata_path = write_macro_indicators(
        silver, output_path=output,
        source_bronze_files=[data.name for data, _ in bronze_paths],
    )
    return silver, bronze_paths, silver_path, metadata_path
