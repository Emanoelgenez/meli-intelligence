"""Build monthly Pix count and value in shared Macro Silver."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from meli_intelligence.sources.bcb.payment_methods_client import PaymentMethodsClient
from meli_intelligence.storage.macro import (
    DEFAULT_MACRO_INDICATORS_PATH,
    merge_macro_indicators,
    read_macro_indicators,
    write_macro_indicators,
)
from meli_intelligence.storage.payment_methods_bronze import (
    DEFAULT_PAYMENT_METHODS_BRONZE_DIR,
    save_payment_methods_bronze,
)
from meli_intelligence.transformations.bcb_payment_methods import (
    normalize_payment_methods_records,
)


PIX_METRICS = (
    "pix_transactions_count_monthly",
    "pix_transactions_value_monthly",
)


def build_bcb_pix_silver(
    start_date: date,
    end_date: date,
    *,
    client: PaymentMethodsClient | None = None,
    bronze_dir: Path = DEFAULT_PAYMENT_METHODS_BRONZE_DIR,
    output_path: Path = DEFAULT_MACRO_INDICATORS_PATH,
) -> tuple[pd.DataFrame, list[tuple[Path, Path]], Path, Path]:
    """Fetch once from the lower-bound month, then filter the requested dates."""
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise TypeError("start_date and end_date must be datetime.date values.")
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    start_month = start_date.strftime("%Y%m")
    owns_client = client is None
    resolved_client = client or PaymentMethodsClient()
    try:
        fetch = resolved_client.fetch_monthly_payment_methods(start_month)
    finally:
        if owns_client:
            resolved_client.close()
    if fetch.requested_start_month != start_month:
        raise ValueError("Payment-method client returned an unexpected lower-bound month.")
    bronze_paths = save_payment_methods_bronze(fetch, bronze_dir=bronze_dir)
    try:
        all_rows = normalize_payment_methods_records(
            fetch.records,
            source_url=fetch.source_url,
            retrieved_at=fetch.retrieved_at,
        )
    except ValueError as exc:
        if str(exc) != "BCB payment-method response returned no observations.":
            raise
        raise ValueError(
            "No Pix observations were returned for the requested period."
        ) from exc
    # Keep this pipeline deliberately fixed-scope even if the registry grows.
    all_rows = all_rows.loc[all_rows["metric_id"].isin(PIX_METRICS)].copy()
    incoming = all_rows.loc[
        all_rows["reference_date"].map(
            lambda reference_date: start_date <= reference_date <= end_date
        )
    ].copy()
    if incoming.empty:
        raise ValueError("No Pix observations were available for the requested range.")
    present = set(incoming["metric_id"])
    missing = sorted(set(PIX_METRICS) - present)
    if missing:
        raise ValueError(
            "BCB payment-method interval is missing required Pix metrics: "
            + ", ".join(missing)
        )
    counts = incoming.groupby("metric_id")["reference_date"].nunique().to_dict()
    if any(counts.get(metric_id, 0) == 0 for metric_id in PIX_METRICS):
        raise ValueError("BCB payment-method interval must contain both Pix metrics.")
    if incoming.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("BCB payment-method rows contain duplicate economic keys.")

    output = Path(output_path)
    silver = (
        merge_macro_indicators(read_macro_indicators(output), incoming)
        if output.exists()
        else incoming.sort_values(["reference_date", "metric_id"]).reset_index(drop=True)
    )
    silver_path, metadata_path = write_macro_indicators(
        silver,
        output_path=output,
        source_bronze_files=[raw.name for raw, _ in bronze_paths],
    )
    return silver, bronze_paths, silver_path, metadata_path
