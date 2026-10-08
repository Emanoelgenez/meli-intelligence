"""Dataset availability checks for read-only UI health reporting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import duckdb

from meli_intelligence.ui.catalog import DatasetSpec, get_dataset_catalog, get_dataset_spec
from meli_intelligence.ui.public_demo import resolve_dataset_path

HealthStatus = Literal["AVAILABLE", "MISSING", "EMPTY", "INVALID"]
_DATE_COLUMNS = ("reference_date", "period_end", "date")


@dataclass(frozen=True)
class DatasetHealth:
    dataset_id: str
    status: HealthStatus
    path: str
    row_count: int | None
    column_count: int | None
    latest_reference_date: date | None
    message: str


def _check(spec: DatasetSpec, path: Path) -> DatasetHealth:
    try:
        path = resolve_dataset_path(spec.dataset_id, spec.default_path, path)
    except FileNotFoundError as exc:
        return DatasetHealth(spec.dataset_id, "MISSING", str(spec.default_path), None, None, None, str(exc))
    except (PermissionError, ValueError, OSError):
        return DatasetHealth(spec.dataset_id, "INVALID", str(spec.default_path), None, None, None, "Public-demo artifact or manifest failed validation; no local fallback.")
    if not path.is_file():
        return DatasetHealth(spec.dataset_id, "MISSING", str(path), None, None, None, "Dataset file is missing.")
    connection = duckdb.connect(database=":memory:")
    try:
        escaped = str(path)
        cursor = connection.execute("SELECT * FROM read_parquet(?) LIMIT 0", [escaped])
        columns = [description[0] for description in cursor.description]
        count = int(connection.execute("SELECT COUNT(*) FROM read_parquet(?)", [escaped]).fetchone()[0])
        if count == 0:
            return DatasetHealth(spec.dataset_id, "EMPTY", str(path), 0, len(columns), None, "Dataset is readable but has no rows.")
        temporal_column = next((column for column in _DATE_COLUMNS if column in columns), None)
        latest = None
        if temporal_column is not None:
            # Column comes from a fixed allowlist of discovered schema names, not user input.
            raw = connection.execute(
                f'SELECT MAX("{temporal_column}") FROM read_parquet(?)', [escaped]
            ).fetchone()[0]
            if raw is not None:
                if isinstance(raw, datetime):
                    latest = raw.date()
                elif isinstance(raw, date):
                    latest = raw
                else:
                    try:
                        latest = date.fromisoformat(str(raw)[:10])
                    except ValueError:
                        latest = None
        return DatasetHealth(spec.dataset_id, "AVAILABLE", str(path), count, len(columns), latest, "Dataset is readable.")
    except Exception as exc:
        return DatasetHealth(spec.dataset_id, "INVALID", str(path), None, None, None, f"Dataset could not be read: {type(exc).__name__}.")
    finally:
        connection.close()


def check_dataset_health(dataset_id: str, *, path: str | Path | None = None) -> DatasetHealth:
    spec = get_dataset_spec(dataset_id)
    return _check(spec, Path(path if path is not None else spec.default_path))


def check_all_datasets() -> tuple[DatasetHealth, ...]:
    return tuple(_check(spec, spec.default_path) for spec in get_dataset_catalog())


def summarize_health(health_records) -> dict:
    records = [asdict(record) if isinstance(record, DatasetHealth) else dict(record) for record in health_records]
    counts = {status.lower() + "_count": sum(item["status"] == status for item in records)
              for status in ("AVAILABLE", "MISSING", "EMPTY", "INVALID")}
    dates = [item.get("latest_reference_date") for item in records if item.get("latest_reference_date") is not None]
    counts["latest_reference_date"] = max(dates) if dates else None
    counts["dataset_count"] = len(records)
    return counts


def health_table(health_records) -> list[dict]:
    return [asdict(record) if isinstance(record, DatasetHealth) else dict(record) for record in health_records]
