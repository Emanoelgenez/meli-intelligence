"""pt-BR presentation, chart-history and MVP navigation regressions."""

from datetime import date
from types import SimpleNamespace

import pandas as pd

from meli_intelligence.ui.pages import BASE_NAVIGATION_OPTIONS, navigation_options
from meli_intelligence.ui.presentation import (
    format_compact_number,
    format_count,
    format_date_br,
    format_metric,
    format_period_label,
    format_status,
)
from meli_intelligence.ui.temporal_charts import (
    chart_frame,
    chart_history,
    quarterly_chart_spec,
)


def _health(dataset_id, status="MISSING", rows=None):
    return SimpleNamespace(dataset_id=dataset_id, status=status, row_count=rows)


def test_brazilian_numbers_dates_periods_and_unavailability():
    assert format_date_br(date(2026, 6, 30)) == "30/06/2026"
    assert format_period_label("QUARTER", date(2026, 6, 30)) == "2º tri. 2026"
    assert format_metric(10_170_000_000, "USD") == "US$ 10,17 bi"
    assert format_compact_number(88_000_000) == "88 milhões"
    assert format_count(88_000_000, "usuários") == "88 milhões de usuários"
    assert format_metric(88_000_000, "users") == "88 milhões de usuários"
    assert format_status("MISSING").startswith("Indisponível")
    assert format_metric(float("nan"), "USD") == "Indisponível"


def test_history_defaults_to_last_twelve_observations_without_filling_gaps():
    frame = pd.DataFrame(
        {
            "period_end": pd.to_datetime(
                ["2021-03-31", "2021-12-31", "2022-09-30"]
                + [f"{year}-06-30" for year in range(2024, 2035)]
            ),
            "value": list(range(14)),
            "unit": "USD",
        }
    )
    short = chart_history(frame, full_history=False)
    complete = chart_history(frame, full_history=True)
    assert len(short) == 12
    assert short.value.tolist() == list(range(2, 14))
    assert len(complete) == len(frame)
    assert len(short.period_end.drop_duplicates()) == len(short)

    chart_data = chart_frame(short, "period_end", "Receita", unit="USD")
    spec = quarterly_chart_spec(chart_data, "period_end", "Receita", unit="USD")
    assert len(spec["encoding"]["x"]["axis"]["values"]) == 12
    assert [item["title"] for item in spec["encoding"]["tooltip"]] == [
        "Período",
        "Receita",
        "Unidade",
        "Definição",
    ]
    assert "transform" not in spec


def test_menu_hides_empty_pages_and_only_adds_available_optional_sections():
    assert BASE_NAVIGATION_OPTIONS == (
        "Visão geral",
        "Financeiro",
        "Comércio",
        "Serviços financeiros",
        "Fontes e qualidade dos dados",
    )
    assert navigation_options([]) == BASE_NAVIGATION_OPTIONS
    records = (
        _health("macro_indicators", "AVAILABLE", 10),
        _health("market_prices", "AVAILABLE", 22),
        _health("market_capitalization", "AVAILABLE", 1),
    )
    options = navigation_options(records)
    assert "Macro" in options
    assert "Mercado" not in options
    assert "PESTEL" not in options and "SWOT" not in options
    opted_in = navigation_options(records, market_opt_in=True)
    assert "Mercado" in opted_in
    assert (
        navigation_options((_health("macro_indicators", "EMPTY", 0),))
        == BASE_NAVIGATION_OPTIONS
    )
