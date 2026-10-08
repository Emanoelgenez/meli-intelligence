"""Derived analytics for qualifier-aware extended operational facts."""

from __future__ import annotations

import pandas as pd


METHODOLOGY_VERSION = "1"
PERIOD_COLUMNS = [
    "period_start",
    "period_end",
    "reference_year",
    "period_type",
    "period_label",
]
ANALYTICS_COLUMNS = [
    "metric_id",
    *PERIOD_COLUMNS,
    "value",
    "unit",
    "formula",
    "source_metrics",
    "definition_context",
    "is_derived",
    "methodology_version",
]
OUTPUT_METRICS = (
    "aum_yoy_growth",
    "credit_portfolio_yoy_growth",
    "npl_15_90_yoy_change_pp",
    "aum_per_fintech_mau",
    "credit_portfolio_per_fintech_mau",
)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=ANALYTICS_COLUMNS)


def _require_columns(facts: pd.DataFrame, required: set[str]) -> None:
    missing = required.difference(facts.columns)
    if missing:
        raise ValueError(
            f"Extended operational facts missing columns: {sorted(missing)}"
        )


def _metric_frame(facts: pd.DataFrame, metric_id: str) -> pd.DataFrame:
    frame = facts.loc[facts["metric_id"] == metric_id].copy()
    if frame.empty:
        return frame
    frame["period_end"] = pd.to_datetime(frame["period_end"])
    if "period_start" not in frame:
        frame["period_start"] = pd.NaT
    else:
        frame["period_start"] = pd.to_datetime(frame["period_start"])
    return frame


def _reject_duplicates(frame: pd.DataFrame, key: list[str], description: str) -> None:
    if frame.duplicated(subset=key, keep=False).any():
        raise ValueError(f"Ambiguous {description}.")


def _finalize(
    frame: pd.DataFrame,
    *,
    metric_id: str,
    unit: str,
    formula: str,
    source_metrics: str,
    definition_context: pd.Series | str,
) -> pd.DataFrame:
    if frame.empty:
        return _empty()
    result = frame[PERIOD_COLUMNS + ["value"]].copy()
    result.insert(0, "metric_id", metric_id)
    result["unit"] = unit
    result["formula"] = formula
    result["source_metrics"] = source_metrics
    result["definition_context"] = definition_context
    result["is_derived"] = True
    result["methodology_version"] = METHODOLOGY_VERSION
    return result[ANALYTICS_COLUMNS]


def calculate_extended_yoy(
    facts: pd.DataFrame,
    metric_id: str,
    *,
    output_metric_id: str | None = None,
    percentage_point_change: bool = False,
) -> pd.DataFrame:
    """Derive exact, like-for-like annual changes from instant facts."""
    _require_columns(
        facts,
        {
            "metric_id", "period_end", "reference_year", "period_type",
            "period_label", "value", "unit", "scope", "value_qualifier",
        },
    )
    current = _metric_frame(facts, metric_id)
    if current.empty:
        return _empty()
    current["_month_day"] = current["period_end"].dt.strftime("%m-%d")
    current["_reference_year"] = current["period_end"].dt.year
    key = ["_reference_year", "_month_day", "unit", "scope"]
    _reject_duplicates(current, key, f"YoY source periods for {metric_id}")

    previous = current[
        key + ["value", "value_qualifier", "period_end", "period_type", "period_label"]
    ].copy()
    previous = previous.rename(
        columns={
            "_reference_year": "_prior_year",
            "value": "previous_value",
            "value_qualifier": "previous_qualifier",
            "period_end": "previous_period_end",
            "period_type": "previous_period_type",
            "period_label": "previous_period_label",
        }
    )
    previous["_reference_year"] = previous["_prior_year"] + 1
    joined = current.merge(
        previous,
        on=["_reference_year", "_month_day", "unit", "scope"],
        how="inner",
        validate="one_to_one",
    )
    joined = joined.loc[
        (joined["period_end"].dt.year - joined["previous_period_end"].dt.year == 1)
        & (joined["period_end"].dt.strftime("%m-%d")
           == joined["previous_period_end"].dt.strftime("%m-%d"))
        & (joined["period_type"] == joined["previous_period_type"])
        & (joined["period_label"] == joined["previous_period_label"])
        & (joined["value_qualifier"] == "exact")
        & (joined["previous_qualifier"] == "exact")
    ].copy()
    if percentage_point_change:
        joined["value"] = joined["value"] - joined["previous_value"]
        out_id = output_metric_id or f"{metric_id}_yoy_change_pp"
        unit = "percentage_points"
        formula = "current_value - previous_year_value"
    else:
        joined = joined.loc[joined["previous_value"] > 0].copy()
        joined["value"] = (
            joined["value"] / joined["previous_value"] - 1.0
        ) * 100.0
        out_id = output_metric_id or f"{metric_id}_yoy_growth"
        unit = "percent"
        formula = "(current_value / previous_year_value - 1) * 100"
    context = (
        "scope=" + joined["scope"].astype(str)
        + ";current_qualifier=" + joined["value_qualifier"].astype(str)
        + ";prior_qualifier=" + joined["previous_qualifier"].astype(str)
    )
    return _finalize(
        joined,
        metric_id=out_id,
        unit=unit,
        formula=formula,
        source_metrics=metric_id,
        definition_context=context,
    )


def calculate_per_fintech_mau(
    extended_facts: pd.DataFrame,
    operational_facts: pd.DataFrame,
    metric_id: str,
) -> pd.DataFrame:
    """Divide an exact extended snapshot by same-date reported Fintech MAU."""
    _require_columns(
        extended_facts,
        {
            "metric_id", "period_end", "reference_year", "period_type",
            "period_label", "value", "unit", "scope", "value_qualifier",
        },
    )
    _require_columns(
        operational_facts,
        {
            "metric_id", "period_end", "reference_year", "period_type",
            "period_label", "value", "unit",
        },
    )
    left = _metric_frame(extended_facts, metric_id)
    mau = _metric_frame(operational_facts, "fintech_mau")
    if left.empty or mau.empty:
        return _empty()
    _reject_duplicates(left, ["period_end", "unit", "scope"], f"{metric_id} snapshot")
    _reject_duplicates(mau, ["period_end"], "Fintech MAU snapshot")
    if "definition_version" in mau:
        mau = mau.rename(
            columns={"definition_version": "mau_definition_version"}
        )
    joined = left.merge(
        mau,
        on="period_end",
        how="inner",
        suffixes=("", "_mau"),
        validate="one_to_one",
    )
    joined = joined.loc[
        (joined["period_type"] == "INSTANT")
        & (joined["period_type_mau"] == "INSTANT")
        & (joined["unit"] == "USD")
        & (joined["unit_mau"] == "users")
        & (joined["value_qualifier"] == "exact")
        & (joined["value_mau"] > 0)
    ].copy()
    if joined.empty:
        return _empty()
    joined["value"] = joined["value"] / joined["value_mau"]
    context = (
        "scope=" + joined["scope"].astype(str)
        + ";qualifier=" + joined["value_qualifier"].astype(str)
        + ";denominator=reported_fintech_mau"
    )
    if "mau_definition_version" in joined:
        context = (
            context
            + ";mau_definition_version="
            + joined["mau_definition_version"].astype(str)
        )
    joined["definition_context"] = context
    return _finalize(
        joined,
        metric_id=f"{metric_id}_per_fintech_mau",
        unit="USD_per_user",
        formula=f"{metric_id} / fintech_mau",
        source_metrics=f"{metric_id};fintech_mau",
        definition_context=joined["definition_context"],
    )


def build_extended_operational_analytics(
    extended_facts: pd.DataFrame,
    operational_facts: pd.DataFrame,
) -> pd.DataFrame:
    """Build V1 extended operational derived metrics."""
    outputs = [
        calculate_extended_yoy(extended_facts, "aum"),
        calculate_extended_yoy(extended_facts, "credit_portfolio"),
        calculate_extended_yoy(
            extended_facts,
            "npl_15_90_total",
            output_metric_id="npl_15_90_yoy_change_pp",
            percentage_point_change=True,
        ),
        calculate_per_fintech_mau(extended_facts, operational_facts, "aum"),
        calculate_per_fintech_mau(
            extended_facts, operational_facts, "credit_portfolio"
        ),
    ]
    non_empty = [frame for frame in outputs if not frame.empty]
    if not non_empty:
        return _empty()
    return pd.concat(non_empty, ignore_index=True).sort_values(
        ["metric_id", "period_end", "period_start"], na_position="first"
    ).reset_index(drop=True)
