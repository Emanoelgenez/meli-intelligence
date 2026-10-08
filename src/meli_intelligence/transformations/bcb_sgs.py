"""Normalize official BCB SGS JSON records into macro Silver rows."""

from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math
from typing import Any

import pandas as pd

from meli_intelligence.metadata.bcb_series import get_bcb_series


INGESTION_VERSION = "1"
MACRO_COLUMNS = [
    "metric_id",
    "source_series_id",
    "reference_date",
    "value",
    "unit",
    "frequency",
    "source",
    "source_url",
    "retrieved_at",
    "ingestion_version",
]


def _parse_reference_date(value: Any, index: int) -> date:
    if not isinstance(value, str):
        raise ValueError(f"BCB SGS record {index} has a non-string data field.")
    try:
        parsed = datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(
            f"BCB SGS record {index} has invalid date {value!r}."
        ) from exc
    if parsed.strftime("%d/%m/%Y") != value:
        raise ValueError(f"BCB SGS record {index} date must use DD/MM/YYYY.")
    return parsed


def _parse_value(value: Any, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"BCB SGS record {index} has invalid valor {value!r}.")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"BCB SGS record {index} has invalid valor {value!r}."
        ) from exc
    if not decimal_value.is_finite():
        raise ValueError(f"BCB SGS record {index} has non-finite valor {value!r}.")
    numeric_value = float(decimal_value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"BCB SGS record {index} is outside float64 range.")
    return numeric_value


def _normalize_reference_date(value: Any, index: int, frequency: str) -> date:
    reference_date = _parse_reference_date(value, index)
    if frequency == "monthly":
        month_end = calendar.monthrange(
            reference_date.year, reference_date.month
        )[1]
        return date(reference_date.year, reference_date.month, month_end)
    return reference_date


def normalize_sgs_payload(
    payload: list[dict[str, Any]],
    series_code: int,
    *,
    source_url: str,
    retrieved_at: str,
    ingestion_version: str = INGESTION_VERSION,
) -> pd.DataFrame:
    """Map official ``data``/``valor`` rows into typed macro records."""
    series = get_bcb_series(series_code)
    if not isinstance(payload, list):
        raise ValueError("BCB SGS payload must be a JSON array.")
    rows = []
    for index, record in enumerate(payload):
        if not isinstance(record, dict) or not {"data", "valor"}.issubset(record):
            raise ValueError(
                f"BCB SGS record {index} must contain data and valor fields."
            )
        rows.append(
            {
                "metric_id": series.metric_id,
                "source_series_id": series.source_series_id,
                "reference_date": _normalize_reference_date(
                    record["data"], index, series.frequency
                ),
                "value": _parse_value(record["valor"], index),
                "unit": series.unit,
                "frequency": series.frequency,
                "source": series.source,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "ingestion_version": ingestion_version,
            }
        )
    frame = pd.DataFrame(rows, columns=MACRO_COLUMNS)
    if frame.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro economic key metric_id + reference_date.")
    if not frame.empty:
        frame = frame.sort_values("reference_date").reset_index(drop=True)
    return frame
