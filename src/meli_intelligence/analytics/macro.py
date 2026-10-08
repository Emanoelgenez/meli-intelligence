"""Deterministic derived analytics over normalized Macro Silver facts."""

from __future__ import annotations

import calendar
import math
from datetime import date
from typing import Any

import pandas as pd


METHODOLOGY_VERSION = "1"
MACRO_ANALYTICS_COLUMNS = [
    "metric_id", "reference_date", "value", "unit", "frequency",
    "source", "source_metric_id", "analytics_kind", "definition_context",
    "previous_reference_date", "previous_value", "source_reference_date",
    "direction_flag_id", "direction_value",
]
EXPECTED_FREQUENCY = {
    "selic_target_annual": "daily",
    "ipca_12m_change": "monthly",
    "usd_brl_sell_rate": "daily",
    "household_free_credit_balance": "monthly",
    "household_free_credit_npl_90d_rate": "monthly",
    "ibc_br_activity_sa_index": "monthly",
    "unemployment_rate_rolling_3m": "rolling_3m_monthly",
    "pix_transactions_count_monthly": "monthly",
    "pix_transactions_value_monthly": "monthly",
}
EXPECTED_UNIT = {
    "selic_target_annual": "percent_per_year",
    "ipca_12m_change": "percent",
    "usd_brl_sell_rate": "brl_per_usd",
    "household_free_credit_balance": "million_brl",
    "household_free_credit_npl_90d_rate": "percent",
    "ibc_br_activity_sa_index": "index",
    "unemployment_rate_rolling_3m": "percent",
    "pix_transactions_count_monthly": "transactions",
    "pix_transactions_value_monthly": "brl",
}


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _month_key(value: date) -> tuple[int, int]:
    return value.year, value.month


def _previous_month(key: tuple[int, int]) -> tuple[int, int]:
    year, month = key
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _prepare_macro_silver(facts: pd.DataFrame) -> pd.DataFrame:
    required = {"metric_id", "reference_date", "value", "unit", "frequency"}
    missing = required.difference(facts.columns)
    if missing:
        raise ValueError(f"Macro Silver missing columns: {sorted(missing)}")
    frame = facts.copy()
    frame["reference_date"] = pd.to_datetime(frame["reference_date"], errors="raise").dt.date
    frame["value"] = pd.to_numeric(frame["value"], errors="raise").astype("float64")
    if frame[["metric_id", "reference_date", "value", "unit", "frequency"]].isna().any().any():
        raise ValueError("Macro Silver analytics inputs cannot contain null required values.")
    if frame.metric_id.astype(str).str.strip().eq("").any():
        raise ValueError("Macro Silver metric_id values cannot be empty.")
    if not frame["value"].map(math.isfinite).all():
        raise ValueError("Macro Silver analytics inputs must be finite.")
    if frame.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate Macro Silver economic key metric_id + reference_date.")
    for metric_id, expected in EXPECTED_FREQUENCY.items():
        rows = frame.loc[frame.metric_id == metric_id]
        if not rows.empty and set(rows.frequency.astype(str)) != {expected}:
            raise ValueError(f"Macro metric {metric_id} must have frequency {expected!r}.")
        unit = EXPECTED_UNIT[metric_id]
        if not rows.empty and set(rows.unit.astype(str)) != {unit}:
            raise ValueError(f"Macro metric {metric_id} must have unit {unit!r}.")
        if not rows.empty and expected != "daily":
            non_month_end = rows.reference_date.map(
                lambda value: value != _month_end(value.year, value.month)
            )
            if non_month_end.any():
                raise ValueError(f"Macro metric {metric_id} must use calendar month-end dates.")
    return frame.sort_values(["metric_id", "reference_date"]).reset_index(drop=True)


def _rows(frame: pd.DataFrame, metric_id: str) -> list[dict[str, Any]]:
    selected = frame.loc[frame.metric_id == metric_id].sort_values("reference_date")
    return selected.to_dict(orient="records")


def _direction(flag_id: str | None, value: float) -> str | None:
    if flag_id is None or value == 0:
        return "unchanged" if flag_id is not None else None
    if flag_id == "inflation_12m_direction":
        return "accelerating" if value > 0 else "decelerating"
    if flag_id == "usd_brl_direction":
        return "depreciating_brl" if value > 0 else "appreciating_brl"
    if flag_id in {"credit_yoy_direction", "pix_count_yoy_direction"}:
        return "expanding" if value > 0 else "contracting"
    return "rising" if value > 0 else "falling"


def _record(
    *,
    metric_id: str,
    reference_date: date,
    value: float,
    unit: str,
    frequency: str,
    source: str,
    source_metric_id: str,
    analytics_kind: str,
    definition_context: str,
    previous: dict[str, Any] | None = None,
    source_reference_date: date | None = None,
    direction_flag_id: str | None = None,
) -> dict[str, Any]:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"Derived macro metric {metric_id} is not finite.")
    return {
        "metric_id": metric_id,
        "reference_date": reference_date,
        "value": numeric,
        "unit": unit,
        "frequency": frequency,
        "source": source,
        "source_metric_id": source_metric_id,
        "analytics_kind": analytics_kind,
        "definition_context": definition_context,
        "previous_reference_date": previous["reference_date"] if previous else None,
        "previous_value": float(previous["value"]) if previous else None,
        "source_reference_date": source_reference_date,
        "direction_flag_id": direction_flag_id,
        "direction_value": _direction(direction_flag_id, numeric),
    }


def _calendar_pairs(rows: list[dict[str, Any]], *, yoy: bool) -> list[tuple[dict, dict]]:
    by_month = {_month_key(row["reference_date"]): row for row in rows}
    pairs = []
    for current in rows:
        key = _month_key(current["reference_date"])
        prior_key = (key[0] - 1, key[1]) if yoy else _previous_month(key)
        previous = by_month.get(prior_key)
        if previous is not None:
            pairs.append((current, previous))
    return pairs


def _change_rows(
    rows: list[dict[str, Any]],
    *,
    output_metric_id: str,
    unit: str,
    formula: str,
    analytics_kind: str,
    frequency: str,
    match: str,
    flag_id: str | None = None,
    percent: bool = False,
    omit_zero_denominator: bool = False,
    extra_context: str = "",
) -> list[dict[str, Any]]:
    outputs = []
    pairs = _calendar_pairs(rows, yoy=match == "same_month_previous_year")
    for current, previous in pairs:
        denominator = float(previous["value"])
        if percent and denominator == 0:
            if omit_zero_denominator:
                continue
            raise ValueError(f"Cannot calculate {output_metric_id} with zero denominator.")
        value = (float(current["value"]) / denominator - 1.0) * 100.0 if percent else float(current["value"]) - denominator
        outputs.append(
            _record(
                metric_id=output_metric_id,
                reference_date=current["reference_date"],
                value=value,
                unit=unit,
                frequency=frequency,
                source=str(current["source"]),
                source_metric_id=str(current["metric_id"]),
                analytics_kind=analytics_kind,
                definition_context=(
                    f"formula={formula};temporal_match={match};"
                    f"source_frequency={current['frequency']};{extra_context}"
                ).rstrip(";"),
                previous=previous,
                direction_flag_id=flag_id,
            )
        )
    return outputs


def _previous_observation_changes(
    rows: list[dict[str, Any]],
    *,
    output_metric_id: str,
    unit: str,
    frequency: str,
    formula: str,
    flag_id: str | None = None,
    extra_context: str = "",
) -> list[dict[str, Any]]:
    outputs = []
    for previous, current in zip(rows, rows[1:]):
        change = float(current["value"]) - float(previous["value"])
        outputs.append(_record(
            metric_id=output_metric_id,
            reference_date=current["reference_date"],
            value=change,
            unit=unit,
            frequency=frequency,
            source=str(current["source"]),
            source_metric_id=str(current["metric_id"]),
            analytics_kind="previous_observation_change",
            definition_context=(
                f"formula={formula};temporal_match=previous_published_observation;"
                f"source_frequency={current['frequency']};{extra_context}"
            ).rstrip(";"),
            previous=previous,
            direction_flag_id=flag_id,
        ))
    return outputs


def build_macro_analytics(macro_silver: pd.DataFrame) -> pd.DataFrame:
    """Return the explicitly approved derived indicators, without I/O."""
    source = _prepare_macro_silver(macro_silver)
    records: list[dict[str, Any]] = []

    # Policy-rate changes use the immediately previous observation in time.
    records += _previous_observation_changes(
        _rows(source, "selic_target_annual"),
        output_metric_id="selic_target_change_pp", unit="percentage_points",
        frequency="daily", formula="current_value - previous_value",
        flag_id="selic_direction",
    )

    records += _change_rows(
        _rows(source, "ipca_12m_change"), output_metric_id="ipca_12m_change_pp",
        unit="percentage_points", formula="current_value - previous_month_value",
        analytics_kind="monthly_percentage_point_change", frequency="monthly",
        match="previous_calendar_month", flag_id="inflation_12m_direction",
    )

    # Monthly FX snapshot is the last available daily quote in each calendar month.
    fx_rows = _rows(source, "usd_brl_sell_rate")
    fx_by_month: dict[tuple[int, int], dict[str, Any]] = {}
    for row in fx_rows:
        fx_by_month[_month_key(row["reference_date"])] = row
    fx_monthly: list[dict[str, Any]] = []
    for (year, month), row in sorted(fx_by_month.items()):
        month_end = _month_end(year, month)
        fx_monthly.append({
            **row,
            "reference_date": month_end,
            "source_reference_date": row["reference_date"],
        })
        records.append(_record(
            metric_id="usd_brl_month_end", reference_date=month_end,
            value=float(row["value"]), unit="brl_per_usd", frequency="monthly",
            source=str(row["source"]),
            source_metric_id="usd_brl_sell_rate", analytics_kind="month_end_snapshot",
            definition_context=(
                "selection=last_daily_observation_available_in_calendar_month;"
                f"source_observation_date={row['reference_date'].isoformat()}"
            ),
            source_reference_date=row["reference_date"],
        ))
    records += _change_rows(
        fx_monthly, output_metric_id="usd_brl_monthly_change_pct", unit="percent",
        formula="(current_value / previous_calendar_month_value - 1) * 100",
        analytics_kind="monthly_percentage_change", frequency="monthly",
        match="previous_calendar_month", percent=True,
        flag_id="usd_brl_direction",
        extra_context="source_is_month_end_snapshot_of_daily_usd_brl",
    )

    records += _change_rows(
        _rows(source, "household_free_credit_balance"),
        output_metric_id="household_free_credit_balance_yoy_growth", unit="percent",
        formula="(current_value / same_calendar_month_previous_year - 1) * 100",
        analytics_kind="yoy_growth", frequency="monthly",
        match="same_month_previous_year", percent=True,
        omit_zero_denominator=True, flag_id="credit_yoy_direction",
    )
    records += _change_rows(
        _rows(source, "household_free_credit_npl_90d_rate"),
        output_metric_id="household_free_credit_npl_90d_yoy_change_pp",
        unit="percentage_points",
        formula="current_value - same_calendar_month_previous_year_value",
        analytics_kind="yoy_percentage_point_change", frequency="monthly",
        match="same_month_previous_year",
        extra_context="BCB delinquency is greater_than_90_days; not_comparable_to_MELI_15_to_90_day_NPL",
    )
    records += _change_rows(
        _rows(source, "ibc_br_activity_sa_index"),
        output_metric_id="ibc_br_activity_mom_change_pct", unit="percent",
        formula="(current_value / previous_calendar_month_value - 1) * 100",
        analytics_kind="monthly_percentage_change", frequency="monthly",
        match="previous_calendar_month", percent=True,
        extra_context="seasonally_adjusted_economic_activity_measured_by_IBC-Br",
    )
    records += _previous_observation_changes(
        _rows(source, "unemployment_rate_rolling_3m"),
        output_metric_id="unemployment_rate_change_pp", unit="percentage_points",
        frequency="rolling_3m_monthly", formula="current_value - previous_published_value",
        flag_id="unemployment_direction",
        extra_context="three_month_rolling_windows_overlap;not_independent_samples",
    )
    records += _change_rows(
        _rows(source, "pix_transactions_count_monthly"),
        output_metric_id="pix_transactions_count_yoy_growth", unit="percent",
        formula="(current_value / same_calendar_month_previous_year - 1) * 100",
        analytics_kind="yoy_growth", frequency="monthly",
        match="same_month_previous_year", percent=True,
        omit_zero_denominator=True, flag_id="pix_count_yoy_direction",
    )
    records += _change_rows(
        _rows(source, "pix_transactions_value_monthly"),
        output_metric_id="pix_transactions_value_yoy_growth", unit="percent",
        formula="(current_value / same_calendar_month_previous_year - 1) * 100",
        analytics_kind="yoy_growth", frequency="monthly",
        match="same_month_previous_year", percent=True,
        omit_zero_denominator=True,
    )

    result = pd.DataFrame(records, columns=MACRO_ANALYTICS_COLUMNS)
    if result.empty:
        return result
    if result.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro analytics economic key metric_id + reference_date.")
    if result[["metric_id", "reference_date", "value", "source_metric_id",
               "analytics_kind", "definition_context"]].isna().any().any():
        raise ValueError("Derived Macro Analytics contains null required output values.")
    if not result.value.map(lambda item: math.isfinite(float(item))).all():
        raise ValueError("Derived Macro Analytics values must be finite.")
    return result.sort_values(["metric_id", "reference_date"]).reset_index(drop=True)


def build_macro_direction_flags(analytics: pd.DataFrame) -> pd.DataFrame:
    """Extract only deterministic descriptive direction labels from analytics."""
    required = {"metric_id", "reference_date", "source_metric_id", "direction_flag_id", "direction_value"}
    missing = required.difference(analytics.columns)
    if missing:
        raise ValueError(f"Macro analytics missing flag columns: {sorted(missing)}")
    flags = analytics.loc[analytics.direction_flag_id.notna(), [
        "metric_id", "reference_date", "source_metric_id", "direction_flag_id", "direction_value"
    ]].rename(columns={"metric_id": "analytics_metric_id", "direction_flag_id": "flag_id", "direction_value": "flag_value"})
    if flags.duplicated(["flag_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro direction flag key flag_id + reference_date.")
    return flags.sort_values(["flag_id", "reference_date"]).reset_index(drop=True)


def pearson_correlation(
    series_a: pd.DataFrame,
    series_b: pd.DataFrame,
    *,
    min_observations: int = 3,
    frequency_a: str,
    frequency_b: str,
) -> dict[str, Any]:
    """Calculate descriptive Pearson correlation after explicit time alignment."""
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2.")
    if frequency_a != frequency_b or frequency_a not in {"monthly", "daily"}:
        raise ValueError("Correlation requires matching explicit daily or monthly frequencies.")
    for name, frame in (("series_a", series_a), ("series_b", series_b)):
        if not {"reference_date", "value"}.issubset(frame.columns):
            raise ValueError(f"{name} requires reference_date and value columns.")
        if frame.duplicated(["reference_date"], keep=False).any():
            raise ValueError(f"{name} has duplicate temporal keys.")
    left = series_a[["reference_date", "value"]].copy()
    right = series_b[["reference_date", "value"]].copy()
    left["reference_date"] = pd.to_datetime(left.reference_date).dt.date
    right["reference_date"] = pd.to_datetime(right.reference_date).dt.date
    if frequency_a == "monthly":
        left["_period"] = left.reference_date.map(_month_key)
        right["_period"] = right.reference_date.map(_month_key)
        if left._period.duplicated(keep=False).any() or right._period.duplicated(keep=False).any():
            raise ValueError("Monthly correlation inputs must have one row per calendar month.")
        left = left.drop(columns="reference_date").rename(columns={"value": "value_a"})
        right = right.drop(columns="reference_date").rename(columns={"value": "value_b"})
        joined = left.merge(right, on="_period", validate="one_to_one")
    else:
        joined = left.merge(right, on="reference_date", suffixes=("_a", "_b"), validate="one_to_one")
    joined["value_a"] = pd.to_numeric(joined["value_a"], errors="coerce")
    joined["value_b"] = pd.to_numeric(joined["value_b"], errors="coerce")
    finite = joined.value_a.map(lambda value: pd.notna(value) and math.isfinite(float(value))) & joined.value_b.map(lambda value: pd.notna(value) and math.isfinite(float(value)))
    joined = joined.loc[finite].reset_index(drop=True)
    if len(joined) < min_observations:
        raise ValueError(f"Insufficient aligned observations: {len(joined)} < {min_observations}.")
    if joined.value_a.nunique() < 2 or joined.value_b.nunique() < 2:
        raise ValueError("Pearson correlation is undefined for a constant series.")
    correlation = float(joined.value_a.corr(joined.value_b, method="pearson"))
    if not math.isfinite(correlation) or not -1.0 <= correlation <= 1.0:
        raise ValueError("Pearson correlation result is not finite and bounded.")
    aligned_dates = (
        [_month_end(year, month) for year, month in joined._period]
        if frequency_a == "monthly"
        else joined.reference_date.tolist()
    )
    return {
        "correlation": correlation,
        "n_observations": len(joined),
        "start_date": min(aligned_dates) if aligned_dates else None,
        "end_date": max(aligned_dates) if aligned_dates else None,
    }
