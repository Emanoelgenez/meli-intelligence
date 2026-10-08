"""Ingest the official BCB SGS daily USD/BRL selling rate."""

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


USD_BRL_SERIES_CODES = (1,)


def build_bcb_usd_brl_silver(
    start_date: date,
    end_date: date,
    *,
    client: BCBSeriesClient | None = None,
    bronze_dir: Path = DEFAULT_BCB_SGS_BRONZE_DIR,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
) -> tuple[pd.DataFrame, list[tuple[Path, Path]], Path, Path]:
    """Fetch SGS 1 and merge its observations into shared macro Silver."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    owns_client = client is None
    resolved_client = client or BCBSeriesClient()
    series = get_bcb_series(USD_BRL_SERIES_CODES[0])
    bronze_paths: list[tuple[Path, Path]] = []
    frames: list[pd.DataFrame] = []
    try:
        fetches = resolved_client.fetch_series(
            USD_BRL_SERIES_CODES[0], start_date, end_date
        )
        for fetch in fetches:
            if fetch.series_code != USD_BRL_SERIES_CODES[0]:
                raise ValueError(
                    "BCB client returned a response for an unexpected series code."
                )
            bronze_paths.append(save_bcb_sgs_bronze(fetch, bronze_dir=bronze_dir))
            frames.append(
                normalize_sgs_payload(
                    fetch.records,
                    USD_BRL_SERIES_CODES[0],
                    source_url=fetch.source_url,
                    retrieved_at=fetch.retrieved_at,
                )
            )
    finally:
        if owns_client:
            resolved_client.close()

    if not frames:
        raise ValueError(
            f"BCB SGS returned no observations for required series 1 ({series.metric_id})."
        )
    incoming = pd.concat(frames, ignore_index=True)
    if incoming.empty:
        raise ValueError(
            f"BCB SGS returned no observations for required series 1 ({series.metric_id})."
        )
    if set(incoming["metric_id"]) != {"usd_brl_sell_rate"}:
        raise ValueError("BCB USD/BRL pipeline received an unexpected metric_id.")
    if set(incoming["source_series_id"]) != {"bcb_sgs:1"}:
        raise ValueError("BCB USD/BRL pipeline received an unexpected source_series_id.")
    if incoming.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("BCB chunks contain duplicate economic keys.")

    output = Path(output_path)
    if output.exists():
        silver = merge_macro_indicators(read_macro_indicators(output), incoming)
    else:
        silver = incoming.sort_values(
            ["reference_date", "metric_id"]
        ).reset_index(drop=True)
    silver_path, metadata_path = write_macro_indicators(
        silver,
        output_path=output,
        source_bronze_files=[data.name for data, _ in bronze_paths],
    )
    return silver, bronze_paths, silver_path, metadata_path
