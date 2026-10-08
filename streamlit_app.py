"""Streamlit entrypoint for the local MELI Intelligence foundation."""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path

# The application checkout owns runtime data, including non-editable installs.
os.environ.setdefault("MELI_PROJECT_ROOT", str(Path(__file__).resolve().parent))

from meli_intelligence.ui.catalog import get_dataset_catalog
from meli_intelligence.ui.filters import BUSINESS_DOMAINS, FilterState
from meli_intelligence.ui.health import check_all_datasets
from meli_intelligence.ui.pages import NAVIGATION_OPTIONS
from meli_intelligence.ui.pages import (
    commerce,
    data_quality_sources,
    executive_overview,
    financial,
    fintech,
    macro,
    market,
    pestel,
    product_evidence,
    swot,
)


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="MELI Intelligence", layout="wide")
    from meli_intelligence.ui.public_demo import render_public_demo_notice

    render_public_demo_notice(st)
    catalog = get_dataset_catalog()
    health = check_all_datasets()
    st.sidebar.title("MELI Intelligence")
    if st.sidebar.button("Reset filters"):
        st.session_state["domain_filter"] = "All"
        st.session_state["start_filter"] = None
        st.session_state["end_filter"] = None
    page = st.sidebar.radio("Navigation", NAVIGATION_OPTIONS)
    if page == "Product Evidence":
        st.sidebar.caption("Business-domain filtering is not shown for this cross-domain page.")
        selected_domain = "All"
    else:
        selected_domain = st.sidebar.selectbox(
            "Business domain", ("All", *sorted(BUSINESS_DOMAINS)), key="domain_filter"
        )
    start_date = st.sidebar.date_input("Start date", value=None, key="start_filter")
    end_date = st.sidebar.date_input("End date", value=None, key="end_filter")
    filters = FilterState(
            business_domain=None if selected_domain == "All" else selected_domain,
            start_date=start_date if isinstance(start_date, date) else None,
            end_date=end_date if isinstance(end_date, date) else None,
        )
    try:
        filters.validate()
    except ValueError as exc:
        st.sidebar.error(str(exc))
        filters = FilterState()
    if page == "Executive Overview":
        executive_overview.render(st, health, catalog, filters)
    elif page == "Financial":
        financial.render(st, health, catalog, filters)
    elif page == "Commerce":
        commerce.render(st, health, catalog, filters)
    elif page == "Fintech":
        fintech.render(st, health, catalog, filters)
    elif page == "Macro":
        macro.render(st, health, catalog, filters)
    elif page == "PESTEL":
        pestel.render(st, health, catalog, filters)
    elif page == "SWOT":
        swot.render(st, health, catalog, filters)
    elif page == "Product Evidence":
        product_evidence.render(st, health, catalog, filters)
    elif page == "Market":
        market.render(st, health, catalog, filters)
    else:
        data_quality_sources.render(st, health, catalog, filters)


if __name__ == "__main__":
    main()
