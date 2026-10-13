"""Chart configuration preserving observed economic dates and quarter labels."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.presentation import (
    format_metric,
    format_period_label,
    format_unit,
)


def chart_history(frame: pd.DataFrame, *, full_history: bool) -> pd.DataFrame:
    """Show the 12 latest observed quarters by default; keep all points on request."""
    if full_history or len(frame) <= 12:
        return frame.copy()
    return frame.sort_values(frame.columns[0]).tail(12).reset_index(drop=True)


def quarterly_chart_spec(
    frame: pd.DataFrame,
    date_column: str,
    value_label: str,
    *,
    unit: str = "USD",
    definition: str = "Valor reportado pela fonte.",
) -> dict:
    """Use a UTC time scale with observed-date ticks; never resample data."""
    if unit in {"million_usd", "million_brl"}:
        symbol = "US$" if unit == "million_usd" else "R$"
        amount_expr = (
            f"abs(datum.value) >= 1000 ? '{symbol} ' + "
            "replace(format(datum.value / 1000, '.2f'), '.', ',') "
            f"+ ' bi' : '{symbol} ' + "
            "replace(format(datum.value, ',.0f'), ',', '.') + ' mi'"
        )
    else:
        symbol = "R$" if unit in {"BRL", "brl"} else "US$"
        amount_expr = (
            f"abs(datum.value) >= 1000000000 ? '{symbol} ' + "
            "replace(format(datum.value / 1000000000, '.2f'), '.', ',') "
            "+ ' bi' : abs(datum.value) >= 1000000 ? "
            f"'{symbol} ' + "
            "replace(format(datum.value / 1000000, '.2f'), '.', ',') "
            f"+ ' mi' : '{symbol} ' + "
            "replace(format(datum.value, ',.0f'), ',', '.')"
        )
    money_axis = {"axis": {"labelExpr": amount_expr}}
    dates = pd.to_datetime(frame[date_column]).dropna().drop_duplicates().sort_values()
    tick_values = dates.dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
    return {
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {
                "field": date_column,
                "type": "temporal",
                "title": "Trimestre de referência",
                "scale": {"type": "utc"},
                "axis": {
                    "values": tick_values,
                    "labelExpr": (
                        "utcquarter(datum.value) + 'º tri. ' "
                        "+ utcyear(datum.value)"
                    ),
                    "labelAngle": -45,
                    "labelAlign": "right",
                    "labelFontSize": 12,
                    "labelColor": "#344454",
                    "labelOverlap": "greedy",
                    "labelSeparation": 6,
                },
            },
            "y": {
                "field": "value",
                "type": "quantitative",
                "title": value_label,
                **(
                    money_axis
                    if unit in {"USD", "BRL", "brl", "million_usd", "million_brl"}
                    else {}
                ),
            },
            "tooltip": [
                {"field": "period_label", "type": "nominal", "title": "Período"},
                {"field": "chart_value", "type": "nominal", "title": value_label},
                {"field": "unit_label", "type": "nominal", "title": "Unidade"},
                {"field": "definition", "type": "nominal", "title": "Definição"},
            ],
        },
    }


def chart_frame(
    frame: pd.DataFrame,
    date_column: str,
    value_label: str,
    *,
    unit: str = "USD",
    definition: str = "Valor reportado pela fonte.",
) -> pd.DataFrame:
    """Add display-only tooltip fields while preserving source dates and values."""
    result = frame.copy()
    result["period_label"] = [
        format_period_label("QUARTER", value) for value in result[date_column]
    ]
    result["chart_value"] = [format_metric(value, unit) for value in result["value"]]
    result["unit_label"] = format_unit(unit)
    result["definition"] = definition
    return result
