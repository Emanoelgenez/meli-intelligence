"""Build the IPCA headline observations in shared macro Silver."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from meli_intelligence.metadata.ibge_series import get_ibge_series
from meli_intelligence.sources.ibge.sidra_client import SIDRAClient
from meli_intelligence.storage.ibge_bronze import (
    DEFAULT_IBGE_SIDRA_BRONZE_DIR,
    save_ibge_sidra_bronze,
)
from meli_intelligence.storage.macro import (
    DEFAULT_MACRO_INDICATORS_PATH,
    merge_macro_indicators,
    read_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.transformations.ibge_sidra import normalize_sidra_payload


IPCA_SERIES = ((1737, 63), (1737, 2265))


def _month(value: date) -> tuple[int, int]:
    return value.year, value.month


def build_ibge_ipca_silver(
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    client: SIDRAClient | None = None,
    bronze_dir: Path = DEFAULT_IBGE_SIDRA_BRONZE_DIR,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
) -> tuple[pd.DataFrame, list[tuple[Path, Path]], Path, Path]:
    """Fetch only the two registered IPCA series and merge into macro Silver."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    owns_client = client is None
    resolved_client = client or SIDRAClient()
    fetches = []
    bronze_paths: list[tuple[Path, Path]] = []
    try:
        for table_id, variable_id in IPCA_SERIES:
            fetch = resolved_client.fetch_variable(table_id, variable_id)
            if (fetch.table_id, fetch.variable_id) != (table_id, variable_id):
                raise ValueError("SIDRA client returned an unexpected table/variable.")
            fetches.append(fetch)
            bronze_paths.append(save_ibge_sidra_bronze(fetch, bronze_dir=bronze_dir))
    finally:
        if owns_client:
            resolved_client.close()

    empty = [
        f"{variable_id} ({get_ibge_series(table_id, variable_id).metric_id})"
        for (table_id, variable_id), fetch in zip(IPCA_SERIES, fetches, strict=True)
        if len(fetch.records) < 2
    ]
    if empty:
        raise ValueError("IBGE SIDRA returned no observations for required IPCA series: " + ", ".join(empty))

    frames = [
        normalize_sidra_payload(
            fetch.records, fetch.table_id, fetch.variable_id,
            source_url=fetch.source_url, retrieved_at=fetch.retrieved_at,
        )
        for fetch in fetches
    ]
    incoming = pd.concat(frames, ignore_index=True)
    if start_date is not None:
        incoming = incoming.loc[
            incoming["reference_date"].map(lambda value: _month(value) >= _month(start_date))
        ]
    if end_date is not None:
        incoming = incoming.loc[
            incoming["reference_date"].map(lambda value: _month(value) <= _month(end_date))
        ]
    expected = {get_ibge_series(*key).metric_id for key in IPCA_SERIES}
    present = set(incoming["metric_id"])
    missing = sorted(expected - present)
    if missing:
        raise ValueError("Requested IPCA interval has no observations for: " + ", ".join(missing))
    if incoming.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro economic key in IBGE SIDRA response.")

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
