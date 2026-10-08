"""Tests for the canonical KPI Dictionary."""

from meli_intelligence.metadata.kpi_dictionary import (
    KPI_DICTIONARY_FIELDS,
    kpi_dictionary_frame,
)


def test_kpi_dictionary_is_complete_and_unique() -> None:
    frame = kpi_dictionary_frame()

    assert len(frame) == 39

    assert list(
        frame.columns
    ) == KPI_DICTIONARY_FIELDS

    assert frame[
        "metric_id"
    ].is_unique

    assert {
        "fintech_mau",
        "unique_active_buyers",
        "gmv",
        "tpv",
        "nimal",
        "items_per_buyer",
        "gmv_per_buyer",
        "acquiring_tpv_share",
        "aum_yoy_growth",
        "credit_portfolio_yoy_growth",
        "npl_15_90_yoy_change_pp",
        "aum_per_fintech_mau",
        "credit_portfolio_per_fintech_mau",
        "selic_target_annual",
        "selic_effective_annual_252",
        "ipca_monthly_change",
        "ipca_12m_change",
        "usd_brl_sell_rate",
        "household_free_credit_balance",
        "household_free_credit_npl_90d_rate",
        "unemployment_rate_rolling_3m",
        "ibc_br_activity_sa_index",
        "retail_sales_volume_mom_sa",
        "pix_transactions_count_monthly",
        "pix_transactions_value_monthly",
        "household_free_credit_balance",
        "household_free_credit_npl_90d_rate",
    }.issubset(
        set(
            frame["metric_id"]
        )
    )
