"""Fundamental financial analytics over canonical Silver facts."""

from __future__ import annotations

from typing import Final

import pandas as pd


PERIOD_KEY: Final[list[str]] = [
    "period_start",
    "period_end",
    "reference_year",
    "period_type",
    "period_label",
]

ANALYTICS_COLUMNS: Final[list[str]] = [
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
    "is_derived",
    "methodology_version",
]

YOY_SOURCE_METRICS: Final[tuple[str, ...]] = (
    "net_revenues_financial_income",
    "gross_profit",
    "operating_income",
    "net_income",
    "operating_cash_flow",
)

MARGIN_SPECS: Final[tuple[tuple[str, str], ...]] = (
    ("gross_profit", "gross_margin"),
    ("operating_income", "operating_margin"),
    ("net_income", "net_margin"),
    (
        "operating_cash_flow",
        "operating_cash_flow_margin",
    ),
)

REVENUE_METRIC: Final[str] = (
    "net_revenues_financial_income"
)

CAPEX_METRIC: Final[str] = (
    "capex_productive_assets"
)

METHODOLOGY_VERSION: Final[str] = "1"


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
    }

    missing = required.difference(
        facts.columns
    )

    if missing:
        raise ValueError(
            "Financial facts are missing required columns: "
            f"{sorted(missing)}"
        )


def _metric_frame(
    facts: pd.DataFrame,
    metric_id: str,
) -> pd.DataFrame:
    frame = facts.loc[
        facts["metric_id"] == metric_id,
        PERIOD_KEY + ["value"],
    ].copy()

    return frame


def _finalize(
    frame: pd.DataFrame,
    *,
    metric_id: str,
    unit: str,
    formula: str,
    source_metrics: str,
    is_derived: bool,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    result = frame[
        PERIOD_KEY + ["value"]
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
    result["is_derived"] = (
        is_derived
    )
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
    """Calculate YoY growth for like-for-like reported periods."""
    current = _metric_frame(
        facts,
        metric_id,
    )

    if current.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    current = current.loc[
        current["period_type"].isin(
            {"QUARTER", "YTD", "FY"}
        )
    ].copy()

    if current.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    current["period_start"] = pd.to_datetime(
        current["period_start"]
    )
    current["period_end"] = pd.to_datetime(
        current["period_end"]
    )

    # period_type + period_label are not sufficient to identify
    # historical economic periods. Older XBRL history can contain
    # more than one period classified under the same label.
    #
    # YoY therefore requires the same calendar shape:
    # e.g. 04-01 -> 06-30 compared only with 04-01 -> 06-30.
    current["_start_month_day"] = (
        current["period_start"]
        .dt.strftime("%m-%d")
    )
    current["_end_month_day"] = (
        current["period_end"]
        .dt.strftime("%m-%d")
    )

    comparison_key = [
        "reference_year",
        "period_type",
        "period_label",
        "_start_month_day",
        "_end_month_day",
    ]

    duplicates = current.duplicated(
        subset=comparison_key,
        keep=False,
    )

    if duplicates.any():
        duplicate_rows = current.loc[
            duplicates,
            comparison_key,
        ].drop_duplicates()

        raise ValueError(
            "Ambiguous periods remain after calendar-signature "
            "matching for metric "
            f"{metric_id}: "
            f"{duplicate_rows.to_dict(orient='records')}"
        )

    previous = current[
        comparison_key + ["value"]
    ].copy()

    previous = previous.rename(
        columns={
            "value": "previous_value"
        }
    )

    previous["reference_year"] = (
        previous["reference_year"] + 1
    )

    merged = current.merge(
        previous,
        how="inner",
        on=comparison_key,
        validate="one_to_one",
    )

    # Percentage growth across zero/negative bases is not
    # treated as analytically comparable in this V1.
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

    return _finalize(
        merged,
        metric_id=f"{metric_id}_yoy_growth",
        unit="percent",
        formula=(
            "(current_value / previous_year_value - 1) * 100"
        ),
        source_metrics=metric_id,
        is_derived=True,
    )

def calculate_margin(
    facts: pd.DataFrame,
    numerator_metric: str,
    output_metric: str,
) -> pd.DataFrame:
    """Calculate a margin against consolidated revenues."""
    numerator = _metric_frame(
        facts,
        numerator_metric,
    ).rename(
        columns={
            "value": "numerator_value"
        }
    )

    revenue = _metric_frame(
        facts,
        REVENUE_METRIC,
    ).rename(
        columns={
            "value": "revenue_value"
        }
    )

    merged = numerator.merge(
        revenue,
        how="inner",
        on=PERIOD_KEY,
        validate="one_to_one",
    )

    merged = merged.loc[
        merged["revenue_value"] != 0
    ].copy()

    merged["value"] = (
        merged["numerator_value"]
        / merged["revenue_value"]
        * 100.0
    )

    return _finalize(
        merged,
        metric_id=output_metric,
        unit="percent",
        formula=(
            f"{numerator_metric} / "
            f"{REVENUE_METRIC} * 100"
        ),
        source_metrics=(
            f"{numerator_metric};"
            f"{REVENUE_METRIC}"
        ),
        is_derived=True,
    )


def calculate_capex(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Expose current productive-assets CAPEX as canonical CAPEX."""
    capex = _metric_frame(
        facts,
        CAPEX_METRIC,
    )

    return _finalize(
        capex,
        metric_id="capex",
        unit="USD",
        formula=CAPEX_METRIC,
        source_metrics=CAPEX_METRIC,
        is_derived=False,
    )


def calculate_free_cash_flow(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate FCF using reported OCF and productive-assets CAPEX."""
    operating_cash_flow = _metric_frame(
        facts,
        "operating_cash_flow",
    ).rename(
        columns={
            "value": "operating_cash_flow_value"
        }
    )

    capex = _metric_frame(
        facts,
        CAPEX_METRIC,
    ).rename(
        columns={
            "value": "capex_value"
        }
    )

    merged = operating_cash_flow.merge(
        capex,
        how="inner",
        on=PERIOD_KEY,
        validate="one_to_one",
    )

    merged["value"] = (
        merged["operating_cash_flow_value"]
        - merged["capex_value"]
    )

    return _finalize(
        merged,
        metric_id="free_cash_flow",
        unit="USD",
        formula=(
            "operating_cash_flow - "
            "capex_productive_assets"
        ),
        source_metrics=(
            "operating_cash_flow;"
            "capex_productive_assets"
        ),
        is_derived=True,
    )


def calculate_free_cash_flow_margin(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate FCF margin for exact matching reported periods."""
    free_cash_flow = (
        calculate_free_cash_flow(
            facts
        )
    )

    if free_cash_flow.empty:
        return pd.DataFrame(
            columns=ANALYTICS_COLUMNS
        )

    free_cash_flow = free_cash_flow[
        PERIOD_KEY + ["value"]
    ].rename(
        columns={
            "value": "free_cash_flow_value"
        }
    )

    revenue = _metric_frame(
        facts,
        REVENUE_METRIC,
    ).rename(
        columns={
            "value": "revenue_value"
        }
    )

    merged = free_cash_flow.merge(
        revenue,
        how="inner",
        on=PERIOD_KEY,
        validate="one_to_one",
    )

    merged = merged.loc[
        merged["revenue_value"] != 0
    ].copy()

    merged["value"] = (
        merged["free_cash_flow_value"]
        / merged["revenue_value"]
        * 100.0
    )

    return _finalize(
        merged,
        metric_id="free_cash_flow_margin",
        unit="percent",
        formula=(
            "free_cash_flow / "
            "net_revenues_financial_income * 100"
        ),
        source_metrics=(
            "operating_cash_flow;"
            "capex_productive_assets;"
            "net_revenues_financial_income"
        ),
        is_derived=True,
    )


def build_financial_analytics(
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Build the V1 fundamental financial analytics dataset."""
    _require_columns(facts)

    outputs: list[pd.DataFrame] = []

    for metric_id in YOY_SOURCE_METRICS:
        outputs.append(
            calculate_yoy_growth(
                facts,
                metric_id,
            )
        )

    for (
        numerator_metric,
        output_metric,
    ) in MARGIN_SPECS:
        outputs.append(
            calculate_margin(
                facts,
                numerator_metric,
                output_metric,
            )
        )

    outputs.append(
        calculate_capex(facts)
    )

    outputs.append(
        calculate_free_cash_flow(
            facts
        )
    )

    outputs.append(
        calculate_free_cash_flow_margin(
            facts
        )
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

    result = result.sort_values(
        by=[
            "metric_id",
            "period_end",
            "period_start",
        ],
        na_position="first",
    ).reset_index(
        drop=True
    )

    return result