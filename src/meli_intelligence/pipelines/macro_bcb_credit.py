"""Ingest BCB household free-credit balance and >90-day NPL series."""

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


CREDIT_SERIES_CODES = (20570, 21112)


def build_bcb_credit_silver(
    start_date: date,
    end_date: date,
    *,
    client: BCBSeriesClient | None = None,
    bronze_dir: Path = DEFAULT_BCB_SGS_BRONZE_DIR,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
) -> tuple[pd.DataFrame, list[tuple[Path, Path]], Path, Path]:
    """Fetch only the two registered household free-credit series."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    owns_client = client is None
    resolved_client = client or BCBSeriesClient()
    bronze_paths: list[tuple[Path, Path]] = []
    frames: list[pd.DataFrame] = []
    missing_series: list[str] = []
    try:
        for series_code in CREDIT_SERIES_CODES:
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
            series_frame = (
                pd.concat(series_frames, ignore_index=True)
                if series_frames
                else pd.DataFrame()
            )
            if series_frame.empty:
                missing_series.append(f"{series_code} ({series.metric_id})")
            else:
                if set(series_frame["metric_id"]) != {series.metric_id}:
                    raise ValueError(
                        f"BCB series {series_code} normalized to an unexpected metric_id."
                    )
                if set(series_frame["source_series_id"]) != {
                    series.source_series_id
                }:
                    raise ValueError(
                        f"BCB series {series_code} normalized to an unexpected source_series_id."
                    )
                frames.append(series_frame)
    finally:
        if owns_client:
            resolved_client.close()

    if missing_series:
        raise ValueError(
            "BCB SGS returned no observations for required credit series: "
            + ", ".join(missing_series)
        )
    incoming = pd.concat(frames, ignore_index=True)
    expected_metric_ids = {
        get_bcb_series(code).metric_id for code in CREDIT_SERIES_CODES
    }
    if set(incoming["metric_id"]) != expected_metric_ids:
        raise ValueError("BCB credit pipeline did not produce both required metrics.")
    if incoming.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("BCB credit responses contain duplicate economic keys.")

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
