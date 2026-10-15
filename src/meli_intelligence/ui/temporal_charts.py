"""Chart configuration preserving observed economic dates and quarter labels."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.presentation import (
    format_metric,
    format_period_label,
    format_unit,
)
from meli_intelligence.ui.public_demo import public_demo_enabled


def chart_history(frame: pd.DataFrame, *, full_history: bool) -> pd.DataFrame:
    """Show the 12 latest observed quarters by default; keep all points on request."""
    if full_history or len(frame) <= 12:
        return frame.copy()
    return frame.sort_values(frame.columns[0]).tail(12).reset_index(drop=True)


def series_coverage(
    frame: pd.DataFrame, date_column: str, *, public_snapshot: bool | None = None
) -> tuple[str, tuple[str, ...]]:
    """Describe chart coverage without implying source completeness."""
    if frame.empty or date_column not in frame:
        return "Sem observações temporais neste recorte.", ()
    dates = pd.to_datetime(frame[date_column], errors="coerce").dropna()
    quarters = sorted(set(dates.dt.to_period("Q")))
    if not quarters:
        return "Sem observações trimestrais neste recorte.", ()
    complete = pd.period_range(quarters[0], quarters[-1], freq="Q")
    missing = tuple(
        format_period_label("QUARTER", period.end_time.date())
        for period in complete
        if period not in set(quarters)
    )
    scope_is_public = (
        public_demo_enabled() if public_snapshot is None else public_snapshot
    )
    scope = (
        "neste pacote público demonstrativo"
        if scope_is_public
        else "na série carregada"
    )
    first = format_period_label("QUARTER", dates.min())
    last = format_period_label("QUARTER", dates.max())
    message = (
        f"Cobertura {scope}: {len(quarters)} trimestres com observação, "
        f"de {first} a {last}."
    )
    if missing:
        message += f" Há {len(missing)} trimestres sem observação neste intervalo."
    else:
        message += " Não há lacunas entre as observações deste intervalo."
    if scope_is_public:
        message += (
            " O snapshot cobre as allowlists aprovadas; não representa "
            "todos os registros corporativos."
        )
    return message, missing


def render_series_coverage(
    st,
    frame: pd.DataFrame,
    date_column: str,
    *,
    full_series: pd.DataFrame | None = None,
) -> None:
    """Show bundle coverage separately from any user-selected date window."""
    coverage_frame = full_series if full_series is not None else frame
    message, missing = series_coverage(coverage_frame, date_column)
    st.caption(message)
    if full_series is not None and not frame.empty:
        all_dates = set(pd.to_datetime(full_series[date_column], errors="coerce"))
        selected_dates = set(pd.to_datetime(frame[date_column], errors="coerce"))
        if selected_dates != all_dates:
            selected, _ = series_coverage(frame, date_column, public_snapshot=False)
            st.caption(f"Recorte dos filtros atuais: {selected}")
    if missing:
        with st.expander("Lacunas na cobertura temporal", expanded=False):
            st.write(", ".join(missing))


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
                        "utcquarter(datum.value) + 'º tri. ' + utcyear(datum.value)"
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
