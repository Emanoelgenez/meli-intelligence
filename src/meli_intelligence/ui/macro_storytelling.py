"""Read-only presentation helpers for persisted Macro facts and analytics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Mapping

import pandas as pd

from meli_intelligence.ui.filters import FilterState, apply_filters
from meli_intelligence.ui.presentation import format_compact_number, format_date

MAX_MACRO_CARDS = 4
MAX_MACRO_OBSERVATIONS = 3


@dataclass(frozen=True)
class MacroMetricSpec:
    dataset_id: str
    metric_id: str
    label: str
    context: str


@dataclass(frozen=True)
class MacroSnapshot:
    metric_id: str
    display_name: str
    value: float
    formatted_value: str
    unit: str
    frequency: str
    reference_date: date
    source: str
    source_url: str
    full_precision_value: str
    context: str


MACRO_PRIORITY = (
    MacroMetricSpec("macro_indicators", "selic_target_annual", "Target Selic rate", "Official BCB policy target."),
    MacroMetricSpec("macro_indicators", "ipca_12m_change", "IPCA over 12 months", "Official twelve-month consumer inflation measure."),
    MacroMetricSpec("macro_indicators", "usd_brl_sell_rate", "USD/BRL sell rate", "Official daily sell quote; original daily frequency is preserved."),
    MacroMetricSpec("macro_indicators", "unemployment_rate_rolling_3m", "Unemployment rate", "Published rolling three-month rate; adjacent windows overlap."),
)
MACRO_ADDITIONAL = (
    MacroMetricSpec("macro_indicators", "selic_effective_annual_252", "Effective Selic rate", "Annualized effective rate based on 252 business days."),
    MacroMetricSpec("macro_indicators", "ipca_monthly_change", "Monthly IPCA change", "Official monthly consumer inflation measure."),
    MacroMetricSpec("macro_indicators", "ibc_br_activity_sa_index", "IBC-Br activity index", "Seasonally adjusted economic activity measured by IBC-Br."),
    MacroMetricSpec("macro_indicators", "retail_sales_volume_mom_sa", "Retail sales volume change", "Official seasonally adjusted monthly change; not recalculated here."),
    MacroMetricSpec("macro_indicators", "household_free_credit_balance", "Household free-credit balance", "Reported BCB household free-credit balance."),
    MacroMetricSpec("macro_indicators", "household_free_credit_npl_90d_rate", "Household delinquency above 90 days", "BCB measure above 90 days; distinct from MELI 15–90 day NPL."),
    MacroMetricSpec("macro_indicators", "pix_transactions_count_monthly", "Monthly Pix transactions", "Monthly BCB payment-method statistics."),
    MacroMetricSpec("macro_indicators", "pix_transactions_value_monthly", "Monthly Pix transaction value", "Monthly BCB payment-method statistics."),
    MacroMetricSpec("macro_analytics", "selic_target_change_pp", "Selic change", "Existing persisted change versus previous observation."),
    MacroMetricSpec("macro_analytics", "ipca_12m_change_pp", "IPCA twelve-month change", "Existing persisted change in the twelve-month rate versus the previous calendar month."),
    MacroMetricSpec("macro_analytics", "usd_brl_month_end", "USD/BRL month-end snapshot", "Existing persisted last available daily quote within the month."),
    MacroMetricSpec("macro_analytics", "usd_brl_monthly_change_pct", "USD/BRL monthly change", "Existing persisted monthly change."),
    MacroMetricSpec("macro_analytics", "household_free_credit_balance_yoy_growth", "Household credit balance YoY", "Existing persisted same-calendar-month annual comparison."),
    MacroMetricSpec("macro_analytics", "household_free_credit_npl_90d_yoy_change_pp", "Household delinquency change YoY", "BCB above-90-day measure; not comparable to MELI 15–90 day NPL."),
    MacroMetricSpec("macro_analytics", "ibc_br_activity_mom_change_pct", "IBC-Br monthly change", "Existing persisted change in seasonally adjusted IBC-Br activity."),
    MacroMetricSpec("macro_analytics", "unemployment_rate_change_pp", "Unemployment rate change", "Existing persisted change between published rolling three-month observations."),
    MacroMetricSpec("macro_analytics", "pix_transactions_count_yoy_growth", "Pix transaction count YoY", "Existing persisted same-calendar-month annual comparison."),
    MacroMetricSpec("macro_analytics", "pix_transactions_value_yoy_growth", "Pix transaction value YoY", "Existing persisted same-calendar-month annual comparison."),
)
MACRO_METRICS = MACRO_PRIORITY + MACRO_ADDITIONAL
MACRO_TREND_METRICS = frozenset({"selic_target_annual"})
MACRO_LABELS = {spec.metric_id: spec.label for spec in MACRO_METRICS}


def _localized_fixed(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def format_macro_value(value: object, unit: str | None) -> str:
    number = _number(value)
    if number is None:
        return "Unavailable"
    if unit == "percent_per_year":
        return f"{_localized_fixed(number, 2)}% a.a."
    if unit == "percent":
        return f"{_localized_fixed(number, 2)}%"
    if unit == "percentage_points":
        return f"{_localized_fixed(number, 2)} p.p."
    if unit == "brl_per_usd":
        return f"R$ {_localized_fixed(number, 4)} por US$"
    if unit in {"brl", "million_brl"}:
        rendered = format_compact_number(number)
        return f"R$ {rendered}" + (" million" if unit == "million_brl" else "")
    if unit == "transactions":
        return f"{format_compact_number(number)} transactions"
    if unit == "index":
        return f"{_localized_fixed(number, 2)} index points"
    return f"{_localized_fixed(number, 2)} {str(unit or 'unit').replace('_', ' ')}"


def _filtered_metric_rows(frame: pd.DataFrame | None, metric_id: str, filters: FilterState | None) -> pd.DataFrame:
    if frame is None or frame.empty or not {"metric_id", "reference_date", "value"}.issubset(frame.columns):
        return pd.DataFrame()
    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date)
    result = apply_filters(frame, date_filters)
    result = result.loc[result.metric_id.astype(str) == metric_id].copy()
    result["_ui_date"] = pd.to_datetime(result.reference_date, errors="coerce")
    result = result.loc[result._ui_date.notna()].copy()
    if result.duplicated(["metric_id", "_ui_date"], keep=False).any():
        raise ValueError(f"Duplicate Macro UI key for metric_id={metric_id!r} and reference_date.")
    return result


def select_macro_snapshots(
    dataset_frames: Mapping[str, pd.DataFrame | None] | None,
    *,
    filters: FilterState | None = None,
    metric_ids: tuple[str, ...] | None = None,
    limit: int = MAX_MACRO_CARDS,
) -> tuple[MacroSnapshot, ...]:
    """Select latest persisted rows by fixed priority, without deriving values."""
    if not isinstance(limit, int) or not 0 <= limit <= len(MACRO_METRICS):
        raise ValueError(f"limit must be between 0 and {len(MACRO_METRICS)}.")
    allowed = {spec.metric_id for spec in MACRO_METRICS}
    if metric_ids is not None and any(metric_id not in allowed for metric_id in metric_ids):
        raise ValueError("Macro metric selection includes a non-allowlisted ID.")
    if limit == 0:
        return ()
    chosen = set(metric_ids) if metric_ids is not None else {spec.metric_id for spec in MACRO_METRICS}
    frames = dataset_frames or {}
    state = (filters or FilterState()).validate()
    snapshots = []
    for spec in MACRO_METRICS:
        if spec.metric_id not in chosen:
            continue
        rows = _filtered_metric_rows(frames.get(spec.dataset_id), spec.metric_id, state)
        if rows.empty:
            continue
        rows = rows.sort_values("_ui_date", kind="mergesort")
        row = rows.iloc[-1]
        value = _number(row.value)
        if value is None:
            continue
        unit = str(row.unit) if pd.notna(row.get("unit")) else ""
        snapshots.append(MacroSnapshot(
            metric_id=spec.metric_id,
            display_name=spec.label,
            value=value,
            formatted_value=format_macro_value(value, unit),
            unit=unit,
            frequency=str(row.frequency) if pd.notna(row.get("frequency")) else "",
            reference_date=pd.Timestamp(row._ui_date).date(),
            source=str(row.source) if pd.notna(row.get("source")) else "Source not reported",
            source_url=str(row.source_url) if pd.notna(row.get("source_url")) else "",
            full_precision_value=f"{row.value} {unit}".strip(),
            context=spec.context,
        ))
        if len(snapshots) >= limit:
            break
    return tuple(snapshots)


def macro_freshness(dataset_frames: Mapping[str, pd.DataFrame | None] | None, *, filters: FilterState | None = None) -> date | None:
    frames = dataset_frames or {}
    state = (filters or FilterState()).validate()
    dates = []
    for spec in MACRO_METRICS:
        rows = _filtered_metric_rows(frames.get(spec.dataset_id), spec.metric_id, state)
        if not rows.empty:
            dates.extend(rows._ui_date.dt.date.tolist())
    return max(dates) if dates else None


def select_macro_trend(
    dataset_frames: Mapping[str, pd.DataFrame | None],
    *,
    metric_id: str = "selic_target_annual",
    filters: FilterState | None = None,
) -> pd.DataFrame:
    if metric_id not in MACRO_TREND_METRICS:
        raise ValueError(f"Macro trend metric {metric_id!r} is not allowlisted.")
    rows = _filtered_metric_rows((dataset_frames or {}).get("macro_indicators"), metric_id, filters)
    if rows.empty:
        return pd.DataFrame(columns=["reference_date", "value"])
    values = rows.apply(lambda row: _number(row.value), axis=1)
    valid = values.notna()
    result = pd.DataFrame({"reference_date": rows.loc[valid, "_ui_date"].dt.date, "value": values.loc[valid].astype(float)})
    return result.sort_values("reference_date", kind="mergesort").reset_index(drop=True)


def select_macro_observations(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    limit: int = MAX_MACRO_OBSERVATIONS,
) -> pd.DataFrame:
    if not isinstance(limit, int) or not 0 <= limit <= MAX_MACRO_OBSERVATIONS:
        raise ValueError(f"limit must be between 0 and {MAX_MACRO_OBSERVATIONS}.")
    columns = ["evidence_id", "evidence_type", "metric_id", "reference_date", "claim", "source", "source_metric_id"]
    if frame is None or frame.empty or not set(columns).issubset(frame.columns):
        return pd.DataFrame(columns=columns)
    state = (filters or FilterState()).validate()
    selected = frame.loc[frame.evidence_type.astype(str) == "OBSERVATION"].copy()
    if "business_domain" in selected.columns:
        selected = selected.loc[selected.business_domain.astype(str) == "Macro"].copy()
    selected = apply_filters(selected, FilterState(start_date=state.start_date, end_date=state.end_date))
    selected["_ui_date"] = pd.to_datetime(selected.reference_date, errors="coerce")
    selected = selected.loc[selected._ui_date.notna()].sort_values(
        ["_ui_date", "evidence_id"], ascending=[False, True], kind="mergesort"
    )
    return selected.head(limit).drop(columns="_ui_date").reset_index(drop=True)
