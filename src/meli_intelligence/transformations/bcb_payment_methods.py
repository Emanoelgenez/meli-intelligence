"""Normalize aggregate monthly Pix fields from BCB payment methods."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any

import pandas as pd

from meli_intelligence.metadata.pix_series import PIX_SERIES


INGESTION_VERSION = "1"
MACRO_COLUMNS = [
    "metric_id", "source_series_id", "reference_date", "value", "unit",
    "frequency", "source", "source_url", "retrieved_at", "ingestion_version",
]


def _month_end(value: Any, index: int) -> date:
    text = str(value)
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError(f"Payment-method row {index} has invalid AnoMes {value!r}.")
    year, month = int(text[:4]), int(text[4:])
    if year < 1 or not 1 <= month <= 12:
        raise ValueError(f"Payment-method row {index} has invalid AnoMes {value!r}.")
    return date(year, month, calendar.monthrange(year, month)[1])


def _number(value: Any, *, index: int, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Payment-method row {index} has invalid {field} {value!r}.")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Payment-method row {index} has invalid {field} {value!r}.") from exc
    if not result.is_finite() or not math.isfinite(float(result)):
        raise ValueError(f"Payment-method row {index} has non-finite {field} {value!r}.")
    if result < 0:
        raise ValueError(f"Payment-method row {index} has negative {field} {value!r}.")
    return result


def normalize_payment_methods_records(
    records: list[dict[str, Any]],
    *,
    source_url: str,
    retrieved_at: str,
    ingestion_version: str = INGESTION_VERSION,
) -> pd.DataFrame:
    """Create precisely two monthly Pix observations for each source row."""
    if not isinstance(records, list) or not records:
        raise ValueError("BCB payment-method response returned no observations.")
    result: list[dict[str, Any]] = []
    observed_months: set[date] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or not {
            "AnoMes", "quantidadePix", "valorPix"
        }.issubset(record):
            raise ValueError(f"Payment-method row {index} is missing required fields.")
        reference_date = _month_end(record["AnoMes"], index)
        if reference_date in observed_months:
            raise ValueError(f"Duplicate payment-method AnoMes {record['AnoMes']!r}.")
        observed_months.add(reference_date)
        for series in PIX_SERIES:
            raw_value = _number(record[series.source_field], index=index, field=series.source_field)
            scaled = raw_value * series.scale_factor
            if series.metric_id == "pix_transactions_count_monthly" and scaled != scaled.to_integral_value():
                raise ValueError(
                    f"Payment-method row {index} quantityPix does not normalize "
                    "to an integer transaction count."
                )
            number = float(scaled)
            if not math.isfinite(number):
                raise ValueError(f"Payment-method row {index} scaled value is not finite.")
            result.append({
                "metric_id": series.metric_id,
                "source_series_id": series.source_series_id,
                "reference_date": reference_date,
                "value": number,
                "unit": series.silver_unit,
                "frequency": series.frequency,
                "source": series.source,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "ingestion_version": ingestion_version,
            })
    frame = pd.DataFrame(result, columns=MACRO_COLUMNS)
    if frame.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro economic key metric_id + reference_date.")
    return frame.sort_values(["reference_date", "metric_id"]).reset_index(drop=True)
