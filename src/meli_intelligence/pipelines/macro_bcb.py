"""Vertical ingestion pipeline for daily BCB Selic SGS series."""

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


SELIC_SERIES_CODES = (432, 1178)


def build_bcb_selic_silver(
    start_date: date,
    end_date: date,
    *,
    client: BCBSeriesClient | None = None,
    bronze_dir: Path = DEFAULT_BCB_SGS_BRONZE_DIR,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
) -> tuple[pd.DataFrame, list[tuple[Path, Path]], Path, Path]:
    """Fetch both registered Selic series and build generic macro Silver."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    owns_client = client is None
    resolved_client = client or BCBSeriesClient()
    bronze_paths: list[tuple[Path, Path]] = []
    frames = []
    missing_series = []
    try:
        for series_code in SELIC_SERIES_CODES:
            series = get_bcb_series(series_code)
            series_frames = []
            for fetch in resolved_client.fetch_series(
                series_code, start_date, end_date
            ):
                if fetch.series_code != series_code:
                    raise ValueError(
                        "BCB client returned a response for an unexpected series code."
                    )
                bronze_paths.append(
                    save_bcb_sgs_bronze(fetch, bronze_dir=bronze_dir)
                )
                series_frames.append(
                    normalize_sgs_payload(
                        fetch.records,
                        series_code,
                        source_url=fetch.source_url,
                        retrieved_at=fetch.retrieved_at,
                    )
                )
            if series_frames:
                series_frame = pd.concat(series_frames, ignore_index=True)
            else:
                series_frame = pd.DataFrame()
            if series_frame.empty:
                missing_series.append(
                    f"{series_code} ({series.metric_id})"
                )
            else:
                frames.append(series_frame)
    finally:
        if owns_client:
            resolved_client.close()

    if missing_series:
        raise ValueError(
            "BCB SGS returned no observations for required Selic series: "
            + ", ".join(missing_series)
        )
    incoming = pd.concat(frames, ignore_index=True)
    if incoming.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("BCB chunks contain duplicate economic keys.")
    if Path(output_path).exists():
        existing = read_macro_indicators(output_path)
        silver = merge_macro_indicators(existing, incoming)
    else:
        silver = incoming.sort_values(
            ["reference_date", "metric_id"]
        ).reset_index(drop=True)
    silver_path, metadata_path = write_macro_indicators(
        silver,
        output_path=output_path,
        source_bronze_files=[data.name for data, _ in bronze_paths],
    )
    return silver, bronze_paths, silver_path, metadata_path
