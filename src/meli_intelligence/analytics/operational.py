"""Derived analytics for canonical MercadoLibre operational KPIs."""

from __future__ import annotations

import pandas as pd


METHODOLOGY_VERSION = "1"

PERIOD_KEY = [
    "period_start",
    "period_end",
    "reference_year",
    "period_type",
    "period_label",
]

ANALYTICS_COLUMNS = [
    "metric_id",
    "period_start",
    "period_end",
    "reference_year",
    "period_type",
    "period_label",
    "value",
    "unit",
    "formula",
    "source_metrics",
    "definition_context",
    "is_derived",
    "methodology_version",
]

GROWTH_METRICS = (
    "fintech_mau",
    "unique_active_buyers",
    "gmv",
    "items_sold",
    "tpv",
    "acquiring_tpv",
    "payment_transactions",
)


def _require_columns(
    facts: pd.DataFrame,
) -> None:
    required = {
        "metric_id",
        "period_start",
        "period_end",
        "reference_year",
        "period_type",
        "period_label",
        "value",
        "unit",
        "definition_version",
    }

    missing = required.difference(
        facts.columns
    )

    if missing:
        raise ValueError(
            "Operational facts missing required columns: "
            f"{sorted(missing)}"
        )


def _metric_frame(
    facts: pd.DataFrame,
    metric_id: str,
) -> pd.DataFrame:
    frame = facts.loc[
        facts["metric_id"] == metric_id,
        PERIOD_KEY
        + [
            "value",
            "definition_version",
        ],
    ].copy()

    if frame.empty:
        return frame

    frame["period_start"] = pd.to_datetime(
        frame["period_start"]
    )

    frame["period_end"] = pd.to_datetime(
        frame["period_end"]
    )

    return frame


def _comparison_family(
    metric_id: str,
    definition_version: str,
) -> str:
    """Map publication versions into explicitly comparable families."""
    if metric_id in {
        "tpv",
        "payment_transactions",
    }:
        if definition_version in {
            "v2_excludes_p2p",
            "v2_recast_excludes_p2p",
        }:
            return "excludes_p2p"

    return definition_version


def _with_calendar_signature(
    frame: pd.DataFrame,
    metric_id: str,
) -> pd.DataFrame:
    result = frame.copy()

    result["_start_month_day"] = (
        result["period_start"]
        .dt.strftime("%m-%d")
        .fillna("")
    )

    result["_end_month_day"] = (
        result["period_end"]
        .dt.strftime("%m-%d")
    )

    result["_comparison_family"] = [
        _comparison_family(
            metric_id,
            str(version),
        )
        for version in result[
            "definition_version"
        ]
    ]

    return result


def _yoy_join(
    facts: pd.DataFrame,
    metric_id: str,
) -> pd.DataFrame:
    current = _metric_frame(
        facts,
        metric_id,
    )

    if current.empty:
        return current

    current = _with_calendar_signature(
        current,
        metric_id,
    )

    join_key = [
        "reference_year",
        "period_type",
        "period_label",
        "_start_month_day",
        "_end_month_day",
        "_comparison_family",
    ]

    duplicate = current.duplicated(
        subset=join_key,
        keep=False,
    )

    if duplicate.any():
        raise ValueError(
            "Ambiguous operational YoY periods for "
            f"{metric_id}."
        )

    previous = current[
        join_key
        + [
            "value",
            "definition_version",
        ]
    ].copy()

    previous = previous.rename(
        columns={
            "value": "previous_value",
            "definition_version": (
                "previous_definition_version"
            ),
        }
    )

    previous["reference_year"] = (
        previous["reference_year"]
        + 1
    )

    merged = current.merge(
        previous,
        how="inner",
        on=join_key,
        validate="one_to_one",
    )

    return merged


def _definition_context(
    current: str,
    previous: str,
) -> str:
    if current == previous:
        return current

    return (
        f"{current};"
        f"prior={previous}"
    )


def _finalize(
    frame: pd.DataFrame,
    *,
    metric_id: str,
    unit: str,
    formula: str,
    source_metrics: str,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    result = frame[
        PERIOD_KEY
        + [
            "value",
            "definition_context",
        ]
    ].copy()

    result.insert(
        0,
        "metric_id",
        metric_id,
    )

    result["unit"] = unit
    result["formula"] = formula
    result["source_metrics"] = (
        source_metrics
    )
    result["is_derived"] = True
    result["methodology_version"] = (
        METHODOLOGY_VERSION
    )

    return result[
        ANALYTICS_COLUMNS
    ]


def calculate_yoy_growth(
    facts: pd.DataFrame,
    metric_id: str,
) -> pd.DataFrame:
    """Calculate like-for-like YoY growth."""
    merged = _yoy_join(
        facts,
        metric_id,
    )

    if merged.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    merged = merged.loc[
        merged["previous_value"] > 0
    ].copy()

    if merged.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    merged["value"] = (
        (
            merged["value"]
            / merged["previous_value"]
        )
        - 1.0
    ) * 100.0

    merged["definition_context"] = [
        _definition_context(
            str(current),
            str(previous),
        )
        for current, previous in zip(
            merged["definition_version"],
            merged[
                "previous_definition_version"
            ],
            strict=True,
        )
    ]

    return _finalize(
        merged,
        metric_id=(
            f"{metric_id}_yoy_growth"
        ),
        unit="percent",
        formula=(
            "(current_value / previous_year_value - 1) * 100"
        ),
        source_metrics=metric_id,
    )


def calculate_nimal_yoy_change(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate NIMAL YoY change in percentage points."""
    merged = _yoy_join(
        facts,
        "nimal",
    )

    if merged.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    merged["value"] = (
        merged["value"]
        - merged["previous_value"]
    )

    merged["definition_context"] = [
        _definition_context(
            str(current),
            str(previous),
        )
        for current, previous in zip(
            merged["definition_version"],
            merged[
                "previous_definition_version"
            ],
            strict=True,
        )
    ]

    return _finalize(
        merged,
        metric_id="nimal_yoy_change_pp",
        unit="percentage_points",
        formula=(
            "current_nimal - previous_year_nimal"
        ),
        source_metrics="nimal",
    )


def _exact_period_join(
    facts: pd.DataFrame,
    *,
    left_metric: str,
    right_metric: str,
) -> pd.DataFrame:
    left = _metric_frame(
        facts,
        left_metric,
    ).rename(
        columns={
            "value": "left_value",
            "definition_version": (
                "left_definition_version"
            ),
        }
    )

    right = _metric_frame(
        facts,
        right_metric,
    ).rename(
        columns={
            "value": "right_value",
            "definition_version": (
                "right_definition_version"
            ),
        }
    )

    if left.empty or right.empty:
        return pd.DataFrame()

    if left.duplicated(
        subset=PERIOD_KEY,
        keep=False,
    ).any():
        raise ValueError(
            f"Duplicate exact periods for {left_metric}."
        )

    if right.duplicated(
        subset=PERIOD_KEY,
        keep=False,
    ).any():
        raise ValueError(
            f"Duplicate exact periods for {right_metric}."
        )

    return left.merge(
        right,
        how="inner",
        on=PERIOD_KEY,
        validate="one_to_one",
    )


def _ratio_definition_context(
    frame: pd.DataFrame,
    left_metric: str,
    right_metric: str,
) -> pd.Series:
    return (
        left_metric
        + ":"
        + frame[
            "left_definition_version"
        ].astype(str)
        + ";"
        + right_metric
        + ":"
        + frame[
            "right_definition_version"
        ].astype(str)
    )


def calculate_items_per_buyer(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate items sold per unique active buyer."""
    merged = _exact_period_join(
        facts,
        left_metric="items_sold",
        right_metric=(
            "unique_active_buyers"
        ),
    )

    if merged.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    merged = merged.loc[
        merged["left_definition_version"]
        == merged["right_definition_version"]
    ].copy()

    merged = merged.loc[
        merged["right_value"] > 0
    ].copy()

    merged["value"] = (
        merged["left_value"]
        / merged["right_value"]
    )

    merged["definition_context"] = (
        _ratio_definition_context(
            merged,
            "items_sold",
            "unique_active_buyers",
        )
    )

    return _finalize(
        merged,
        metric_id="items_per_buyer",
        unit="items_per_buyer",
        formula=(
            "items_sold / unique_active_buyers"
        ),
        source_metrics=(
            "items_sold;"
            "unique_active_buyers"
        ),
    )


def calculate_gmv_per_buyer(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate reported USD GMV per unique active buyer."""
    merged = _exact_period_join(
        facts,
        left_metric="gmv",
        right_metric=(
            "unique_active_buyers"
        ),
    )

    if merged.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    merged = merged.loc[
        merged["left_definition_version"]
        == merged["right_definition_version"]
    ].copy()

    merged = merged.loc[
        merged["right_value"] > 0
    ].copy()

    merged["value"] = (
        merged["left_value"]
        / merged["right_value"]
    )

    merged["definition_context"] = (
        _ratio_definition_context(
            merged,
            "gmv",
            "unique_active_buyers",
        )
    )

    return _finalize(
        merged,
        metric_id="gmv_per_buyer",
        unit="USD_per_buyer",
        formula=(
            "gmv / unique_active_buyers"
        ),
        source_metrics=(
            "gmv;"
            "unique_active_buyers"
        ),
    )


def calculate_acquiring_tpv_share(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate acquiring TPV as a share of total TPV."""
    merged = _exact_period_join(
        facts,
        left_metric="acquiring_tpv",
        right_metric="tpv",
    )

    if merged.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    merged = merged.loc[
        merged["right_value"] != 0
    ].copy()

    merged["value"] = (
        merged["left_value"]
        / merged["right_value"]
        * 100.0
    )

    merged["definition_context"] = (
        _ratio_definition_context(
            merged,
            "acquiring_tpv",
            "tpv",
        )
    )

    return _finalize(
        merged,
        metric_id="acquiring_tpv_share",
        unit="percent",
        formula=(
            "acquiring_tpv / tpv * 100"
        ),
        source_metrics=(
            "acquiring_tpv;tpv"
        ),
    )


def build_operational_analytics(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Build V1 derived operational analytics."""
    _require_columns(
        facts
    )

    outputs: list[pd.DataFrame] = []

    for metric_id in GROWTH_METRICS:
        outputs.append(
            calculate_yoy_growth(
                facts,
                metric_id,
            )
        )

    outputs.extend(
        [
            calculate_nimal_yoy_change(
                facts
            ),
            calculate_items_per_buyer(
                facts
            ),
            calculate_gmv_per_buyer(
                facts
            ),
            calculate_acquiring_tpv_share(
                facts
            ),
        ]
    )

    non_empty = [
        frame
        for frame in outputs
        if not frame.empty
    ]

    if not non_empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    result = pd.concat(
        non_empty,
        ignore_index=True,
    )

    return result.sort_values(
        by=[
            "metric_id",
            "period_end",
            "period_start",
        ],
        na_position="first",
    ).reset_index(
        drop=True
    )