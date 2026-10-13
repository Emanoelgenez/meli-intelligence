"""Streamlit entrypoint for the local MELI Intelligence foundation."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

# The application checkout owns runtime data, including non-editable installs.
os.environ.setdefault("MELI_PROJECT_ROOT", str(Path(__file__).resolve().parent))

from meli_intelligence.ui.catalog import get_dataset_catalog
from meli_intelligence.ui.filters import BUSINESS_DOMAINS, FilterState
from meli_intelligence.ui.health import check_all_datasets
from meli_intelligence.ui.pages import (
    commerce,
    data_quality_sources,
    executive_overview,
    financial,
    fintech,
    macro,
    market,
    navigation_options,
    pestel,
    product_evidence,
    swot,
)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="MELI Intelligence", layout="wide")
    from meli_intelligence.ui.presentation import format_date_br
    from meli_intelligence.ui.public_demo import REFERENCE_DATE, public_demo_enabled

    if public_demo_enabled():
        st.info(
            f"Modo de demonstração · recorte estático selecionado até "
            f"{format_date_br(REFERENCE_DATE)} (v1). Cobertura parcial: "
            "Financeiro, Comércio e Serviços financeiros. Dados de mercado "
            "não incluídos. Outras áreas podem estar intencionalmente indisponíveis."
        )
        st.caption(
            "Fontes: divulgações do Mercado Livre via SEC EDGAR. Projeto "
            "independente, sem endosso ou vínculo com a SEC ou o Mercado Livre."
        )
    catalog = get_dataset_catalog()
    health = check_all_datasets()
    st.markdown(
        """<style>
        .stApp { color: #17212b; }
        [data-testid="stCaptionContainer"] {
            color: #344454; font-size: 0.95rem; line-height: 1.4;
        }
        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: #344454 !important; opacity: 1 !important;
        }
        [data-testid="stMetric"] { padding: 1rem; border: 1px solid #d5dde5;
            border-radius: 0.6rem; background: #fff; }
        h1, h2, h3 { letter-spacing: -0.02em; }
        </style>""",
        unsafe_allow_html=True,
    )
    st.sidebar.title("MELI Intelligence")
    if st.sidebar.button("Limpar filtros"):
        st.session_state["domain_filter"] = "Todas"
        st.session_state["start_filter"] = None
        st.session_state["end_filter"] = None
    market_opt_in = (
        os.getenv("MELI_ENABLE_MARKET_PAGE", "0").strip() == "1"
        and not public_demo_enabled()
    )
    options = navigation_options(health, market_opt_in=market_opt_in)
    page = st.sidebar.radio("Navegação", options)
    from meli_intelligence.ui.presentation import DOMAIN_LABELS

    domain_options = (
        "Todas",
        *[DOMAIN_LABELS.get(item, item) for item in sorted(BUSINESS_DOMAINS)],
    )
    domain_keys = {DOMAIN_LABELS.get(item, item): item for item in BUSINESS_DOMAINS}
    if st.session_state.get("domain_filter") == "All":
        st.session_state["domain_filter"] = "Todas"
    if page == "Product Evidence":
        st.sidebar.caption(
            "Business-domain filtering is not shown for this cross-domain page."
        )
        selected_domain = None
    else:
        selected_domain = st.sidebar.selectbox(
            "Área de negócio", domain_options, key="domain_filter"
        )
        selected_domain = (
            domain_keys.get(selected_domain) if selected_domain != "Todas" else None
        )
    start_date = st.sidebar.date_input(
        "Data inicial", value=None, key="start_filter", format="DD/MM/YYYY"
    )
    end_date = st.sidebar.date_input(
        "Data final", value=None, key="end_filter", format="DD/MM/YYYY"
    )
    filters = FilterState(
        business_domain=selected_domain,
        start_date=start_date if isinstance(start_date, date) else None,
        end_date=end_date if isinstance(end_date, date) else None,
    )
    try:
        filters.validate()
    except ValueError:
        st.sidebar.error(
            "Período inválido: a data inicial deve ser anterior ou igual à data final."
        )
        filters = FilterState()
    if page == "Visão geral":
        executive_overview.render(st, health, catalog, filters)
    elif page == "Financeiro":
        financial.render(st, health, catalog, filters)
    elif page == "Comércio":
        commerce.render(st, health, catalog, filters)
    elif page == "Serviços financeiros":
        fintech.render(st, health, catalog, filters)
    elif page == "Macro":
        macro.render(st, health, catalog, filters)
    elif page == "Mercado":
        market.render(st, health, catalog, filters)
    elif page == "Product Evidence":
        product_evidence.render(st, health, catalog, filters)
    elif page == "PESTEL":
        pestel.render(st, health, catalog, filters)
    elif page == "SWOT":
        swot.render(st, health, catalog, filters)
    else:
        data_quality_sources.render(st, health, catalog, filters)


if __name__ == "__main__":
    main()
