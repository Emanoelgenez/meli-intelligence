"""Streamlit page renderers; importing this package starts no UI runtime."""

BASE_NAVIGATION_OPTIONS = (
    "Visão geral",
    "Financeiro",
    "Comércio",
    "Serviços financeiros",
    "Fontes e qualidade dos dados",
)
NAVIGATION_OPTIONS = (
    "Executive Overview",
    "Financial",
    "Commerce",
    "Fintech",
    "Macro",
    "PESTEL",
    "SWOT",
    "Product Evidence",
    "Market",
    "Data Quality & Sources",
)


def navigation_options(
    health_records, *, market_opt_in: bool = False
) -> tuple[str, ...]:
    """Expose optional sections only when local data and policy allow them."""
    options = list(BASE_NAVIGATION_OPTIONS)
    health = {item.dataset_id: item for item in health_records}
    macro = health.get("macro_indicators")
    if macro is not None and macro.status == "AVAILABLE" and (macro.row_count or 0) > 0:
        options.insert(4, "Macro")
    market = health.get("market_prices")
    if (
        market_opt_in
        and market is not None
        and market.status == "AVAILABLE"
        and (market.row_count or 0) > 0
    ):
        options.insert(-1, "Mercado")
    return tuple(options)
