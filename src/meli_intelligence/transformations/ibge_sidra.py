"""Normalize header-described SIDRA rows into shared macro Silver."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, InvalidOperation
import math
import re
import unicodedata
from typing import Any

import pandas as pd

from meli_intelligence.metadata.ibge_series import get_ibge_series


INGESTION_VERSION = "1"
MACRO_COLUMNS = [
    "metric_id", "source_series_id", "reference_date", "value", "unit",
    "frequency", "source", "source_url", "retrieved_at", "ingestion_version",
]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().casefold()


def _dimension(headers: dict[str, Any], term: str) -> tuple[str, str]:
    matches = []
    for code_key, code_label in headers.items():
        if not re.fullmatch(r"D\d+C", code_key):
            continue
        name_key = code_key[:-1] + "N"
        name_label = headers.get(name_key)
        labels = _norm(code_label), _norm(name_label)
        if any(term in label for label in labels):
            matches.append((code_key, name_key))
    if len(matches) != 1:
        raise ValueError(f"SIDRA header must identify exactly one {term} dimension.")
    return matches[0]


def _classification_dimension(
    headers: dict[str, Any], dimension_name: str
) -> tuple[str, str]:
    """Find a classification dimension by its header label, independent of Dn."""
    expected = _norm(dimension_name)
    alternatives = {expected}
    if expected.startswith("tipos de "):
        alternatives.add(expected.replace("tipos de ", "tipo de ", 1))
    matches = []
    for code_key, code_label in headers.items():
        if not re.fullmatch(r"D\d+C", code_key):
            continue
        name_key = code_key[:-1] + "N"
        name_label = headers.get(name_key)
        labels = (_norm(code_label), _norm(name_label))
        if any(label in alternatives for label in labels):
            matches.append((code_key, name_key))
    if len(matches) != 1:
        raise ValueError(
            "SIDRA header must identify exactly one classification dimension "
            f"{dimension_name!r}."
        )
    return matches[0]


def _header_and_rows(payload: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = [
        row for row in payload
        if any(_norm(value) == "valor" for value in row.values())
        and any("nivel territorial" in _norm(value) for value in row.values())
        and any("variavel" in _norm(value) for value in row.values())
        and any(
            any(term in _norm(value) for term in ("mes", "periodo", "trimestre movel"))
            for value in row.values()
        )
    ]
    if len(candidates) != 1:
        raise ValueError("SIDRA payload must contain one recognizable semantic header.")
    header = candidates[0]
    rows = [row for row in payload if row is not header]
    return header, rows


def _find_header_key(header: dict[str, Any], label: str) -> str:
    matches = [key for key, value in header.items() if _norm(value) == _norm(label)]
    if len(matches) != 1:
        raise ValueError(f"SIDRA header must identify exactly one {label!r} field.")
    return matches[0]


def _period_dimension(header: dict[str, Any]) -> tuple[str, str]:
    matches = []
    for code_key, code_label in header.items():
        if not re.fullmatch(r"D\d+C", code_key):
            continue
        name_key = code_key[:-1] + "N"
        labels = (_norm(code_label), _norm(header.get(name_key)))
        if any(any(term in label for term in ("mes", "periodo", "trimestre movel")) for label in labels):
            matches.append((code_key, name_key))
    if len(matches) != 1:
        raise ValueError("SIDRA header must identify exactly one monthly period dimension.")
    return matches[0]


def _parse_month(value: Any, index: int) -> date:
    text = str(value)
    if not re.fullmatch(r"\d{6}", text):
        raise ValueError(f"SIDRA row {index} has invalid monthly period {value!r}.")
    year, month = int(text[:4]), int(text[4:])
    if month < 1 or month > 12:
        raise ValueError(f"SIDRA row {index} has invalid monthly period {value!r}.")
    return date(year, month, calendar.monthrange(year, month)[1])


def _parse_value(value: Any, index: int) -> float | None:
    text = "" if value is None else str(value).strip()
    if text in {"...", ".."}:
        return None
    if text == "-":
        return 0.0
    if not text:
        raise ValueError(f"SIDRA row {index} has an empty value.")
    text = text.replace(",", ".")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"SIDRA row {index} has non-numeric value {value!r}.") from exc
    if not number.is_finite() or not math.isfinite(float(number)):
        raise ValueError(f"SIDRA row {index} has non-finite value {value!r}.")
    return float(number)


def normalize_sidra_payload(
    payload: list[dict[str, Any]], table_id: int, variable_id: int, *,
    source_url: str, retrieved_at: str, ingestion_version: str = INGESTION_VERSION,
) -> pd.DataFrame:
    series = get_ibge_series(table_id, variable_id)
    if not isinstance(payload, list) or not payload:
        raise ValueError("IBGE SIDRA returned no observations.")
    header, rows = _header_and_rows(payload)
    value_key = _find_header_key(header, "Valor")
    level_code_key = _find_header_key(header, "Nível Territorial (Código)")
    level_name_key = _find_header_key(header, "Nível Territorial")
    variable_code_key, variable_name_key = _dimension(header, "variavel")
    period_code_key, _ = _period_dimension(header)
    expected_name = _norm(series.display_name)
    classification_columns = []
    for classification in series.classification_filters:
        dimension_name = classification.dimension_name
        expected_category = classification.category_name
        code_key, name_key = _classification_dimension(header, dimension_name)
        category_values = {_norm(row.get(name_key, "")) for row in rows}
        matching_categories = {
            value for value in category_values if value == _norm(expected_category)
        }
        if not matching_categories:
            raise ValueError(
                f"SIDRA classification category {expected_category!r} was not found "
                f"in dimension {dimension_name!r}."
            )
        matching_codes = {
            str(row.get(code_key, "")).strip()
            for row in rows
            if _norm(row.get(name_key, "")) == _norm(expected_category)
        }
        if (
            len(matching_categories) != 1
            or matching_codes != {str(classification.category_id)}
        ):
            raise ValueError(
                f"SIDRA classification category {expected_category!r} is ambiguous."
            )
        classification_columns.append((code_key, name_key, _norm(expected_category)))
    result = []
    for index, row in enumerate(rows, start=1):
        if not set(header).issubset(row):
            raise ValueError(f"SIDRA row {index} does not match the declared header.")
        territory = _norm(row[level_name_key])
        if territory not in {"brasil", "brazil"} or str(row[level_code_key]) != "1":
            raise ValueError(f"SIDRA row {index} is not national Brazil territory.")
        if str(row[variable_code_key]) != str(variable_id):
            raise ValueError(
                f"SIDRA row {index} variable {row[variable_code_key]!r} "
                f"does not match requested variable {variable_id}."
            )
        if _norm(row[variable_name_key]) != expected_name:
            raise ValueError(
                f"SIDRA variable label {row[variable_name_key]!r} does not match "
                f"registered semantics {series.display_name!r}."
            )
        selected = True
        for code_key, name_key, expected_category in classification_columns:
            category_name = _norm(row[name_key])
            if not category_name:
                raise ValueError(f"SIDRA row {index} has an empty classification label.")
            if category_name != expected_category:
                selected = False
                break
            if not str(row.get(code_key, "")).strip():
                raise ValueError(f"SIDRA row {index} has an empty classification code.")
        if not selected:
            continue
        reference_date = _parse_month(row[period_code_key], index)
        numeric_value = _parse_value(row[value_key], index)
        if numeric_value is None:
            continue
        result.append({
            "metric_id": series.metric_id,
            "source_series_id": series.source_series_id,
            "reference_date": reference_date,
            "value": numeric_value,
            "unit": series.unit,
            "frequency": series.frequency,
            "source": series.source,
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "ingestion_version": ingestion_version,
        })
    frame = pd.DataFrame(result, columns=MACRO_COLUMNS)
    if frame.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro economic key metric_id + reference_date.")
    return frame.sort_values("reference_date").reset_index(drop=True)
