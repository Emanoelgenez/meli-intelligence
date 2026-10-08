"""Canonical KPI Dictionary for MELI Intelligence."""

from __future__ import annotations

import pandas as pd


KPI_DICTIONARY_FIELDS = [
    "metric_id",
    "canonical_name",
    "display_name",
    "description",
    "formula",
    "unit",
    "frequency",
    "source",
    "business_domain",
    "higher_is_better",
    "notes",
]


KPI_DICTIONARY: tuple[dict, ...] = (
    {
        "metric_id": "fintech_mau",
        "canonical_name": "fintech_monthly_active_users",
        "display_name": "Fintech MAU",
        "description": (
            "Monthly active Mercado Pago users as defined "
            "in the applicable earnings release."
        ),
        "formula": "reported",
        "unit": "users",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Fintech",
        "higher_is_better": True,
        "notes": (
            "Definition changes from Q1 2026. "
            "Comparisons must respect definition_version."
        ),
    },
    {
        "metric_id": "unique_active_buyers",
        "canonical_name": "unique_active_buyers",
        "display_name": "Unique Active Buyers",
        "description": (
            "Users performing at least one qualifying purchase "
            "during the reported period."
        ),
        "formula": "reported",
        "unit": "users",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Commerce",
        "higher_is_better": True,
        "notes": (
            "From Q2 2025 the reported indicator includes "
            "food delivery transactions."
        ),
    },
    {
        "metric_id": "gmv",
        "canonical_name": "gross_merchandise_volume",
        "display_name": "GMV",
        "description": (
            "Gross merchandise volume reported by MercadoLibre."
        ),
        "formula": "reported",
        "unit": "USD",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Commerce",
        "higher_is_better": True,
        "notes": (
            "Food delivery is included from Q2 2025. "
            "Values are reported USD, not FX-neutral."
        ),
    },
    {
        "metric_id": "items_sold",
        "canonical_name": "items_sold",
        "display_name": "Items Sold",
        "description": (
            "Number of items sold through the commerce platform."
        ),
        "formula": "reported",
        "unit": "items",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Commerce",
        "higher_is_better": True,
        "notes": (
            "From Q2 2025 the indicator includes food delivery. "
            "Items shipped is not substituted for items sold."
        ),
    },
    {
        "metric_id": "tpv",
        "canonical_name": "total_payment_volume",
        "display_name": "Total Payment Volume",
        "description": (
            "Total payment volume processed by Mercado Pago."
        ),
        "formula": "reported",
        "unit": "USD",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Fintech",
        "higher_is_better": True,
        "notes": (
            "Current methodology excludes peer-to-peer "
            "transactions. 2023 comparatives may be recast."
        ),
    },
    {
        "metric_id": "acquiring_tpv",
        "canonical_name": "acquiring_total_payment_volume",
        "display_name": "Acquiring TPV",
        "description": (
            "Payment volume processed through acquiring solutions."
        ),
        "formula": "reported",
        "unit": "USD",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Fintech",
        "higher_is_better": True,
        "notes": (
            "Used together with TPV to measure acquiring mix."
        ),
    },
    {
        "metric_id": "payment_transactions",
        "canonical_name": "total_payment_transactions",
        "display_name": "Payment Transactions",
        "description": (
            "Total number of payment transactions."
        ),
        "formula": "reported",
        "unit": "transactions",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Fintech",
        "higher_is_better": True,
        "notes": (
            "Current methodology excludes peer-to-peer "
            "transactions. 2023 comparatives may be recast."
        ),
    },
    {
        "metric_id": "nimal",
        "canonical_name": "net_interest_margin_after_losses",
        "display_name": "NIMAL",
        "description": (
            "Credit profitability/risk metric reported "
            "by MercadoLibre."
        ),
        "formula": "reported",
        "unit": "percent",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Credit",
        "higher_is_better": None,
        "notes": (
            "Changes are analyzed in percentage points, "
            "not percentage growth."
        ),
    },

    {
        "metric_id": "aum",
        "canonical_name": "assets_under_management",
        "display_name": "AUM",
        "description": (
            "Assets under management reported for Mercado Pago."
        ),
        "formula": "reported",
        "unit": "USD",
        "frequency": "irregular_quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Fintech",
        "higher_is_better": True,
        "notes": (
            "Some disclosures are approximate and are preserved "
            "with value_qualifier."
        ),
    },
    {
        "metric_id": "credit_portfolio",
        "canonical_name": "total_credit_portfolio",
        "display_name": "Credit Portfolio",
        "description": (
            "Total Mercado Pago credit portfolio."
        ),
        "formula": "reported",
        "unit": "USD",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Credit",
        "higher_is_better": None,
        "notes": (
            "Growth must be interpreted together with NPL and NIMAL. "
            "Lower-bound wording is preserved when applicable."
        ),
    },
    {
        "metric_id": "npl_15_90_total",
        "canonical_name": "total_portfolio_15_90_day_npl",
        "display_name": "15-90 Day NPL",
        "description": (
            "15-90 day non-performing loan ratio for the "
            "total credit portfolio."
        ),
        "formula": "reported",
        "unit": "percent",
        "frequency": "quarterly_reporting",
        "source": "SEC EDGAR earnings release exhibit",
        "business_domain": "Credit",
        "higher_is_better": False,
        "notes": (
            "Total-portfolio scope only. Credit-card-specific "
            "NPL observations are not substituted."
        ),
    },

    # Derived growth metrics
    *tuple(
        {
            "metric_id": f"{metric}_yoy_growth",
            "canonical_name": f"{metric}_year_over_year_growth",
            "display_name": f"{display} YoY Growth",
            "description": (
                f"Year-over-year growth in {display} using "
                "definition-compatible periods."
            ),
            "formula": (
                "(current_value / previous_year_value - 1) * 100"
            ),
            "unit": "percent",
            "frequency": "quarterly_reporting",
            "source": "derived from Operational Silver",
            "business_domain": domain,
            "higher_is_better": True,
            "notes": (
                "Only like-for-like calendar periods and "
                "compatible definition families are compared."
            ),
        }
        for metric, display, domain in (
            (
                "fintech_mau",
                "Fintech MAU",
                "Fintech",
            ),
            (
                "unique_active_buyers",
                "Unique Active Buyers",
                "Commerce",
            ),
            (
                "gmv",
                "GMV",
                "Commerce",
            ),
            (
                "items_sold",
                "Items Sold",
                "Commerce",
            ),
            (
                "tpv",
                "TPV",
                "Fintech",
            ),
            (
                "acquiring_tpv",
                "Acquiring TPV",
                "Fintech",
            ),
            (
                "payment_transactions",
                "Payment Transactions",
                "Fintech",
            ),
        )
    ),

    {
        "metric_id": "nimal_yoy_change_pp",
        "canonical_name": "nimal_year_over_year_change_pp",
        "display_name": "NIMAL YoY Change",
        "description": (
            "Year-over-year change in NIMAL."
        ),
        "formula": (
            "current_nimal - previous_year_nimal"
        ),
        "unit": "percentage_points",
        "frequency": "quarterly_reporting",
        "source": "derived from Operational Silver",
        "business_domain": "Credit",
        "higher_is_better": None,
        "notes": (
            "Reported as percentage-point change."
        ),
    },
    {
        "metric_id": "items_per_buyer",
        "canonical_name": "items_sold_per_unique_active_buyer",
        "display_name": "Items per Buyer",
        "description": (
            "Items sold divided by unique active buyers "
            "for the exact same reported period."
        ),
        "formula": (
            "items_sold / unique_active_buyers"
        ),
        "unit": "items_per_buyer",
        "frequency": "quarterly_reporting",
        "source": "derived from Operational Silver",
        "business_domain": "Commerce",
        "higher_is_better": True,
        "notes": (
            "Engagement/intensity proxy; not a company-reported KPI."
        ),
    },
    {
        "metric_id": "gmv_per_buyer",
        "canonical_name": "gmv_per_unique_active_buyer",
        "display_name": "GMV per Buyer",
        "description": (
            "GMV divided by unique active buyers for the "
            "exact same reported period."
        ),
        "formula": (
            "gmv / unique_active_buyers"
        ),
        "unit": "USD_per_buyer",
        "frequency": "quarterly_reporting",
        "source": "derived from Operational Silver",
        "business_domain": "Commerce",
        "higher_is_better": True,
        "notes": (
            "Commerce intensity proxy; not a company-reported KPI."
        ),
    },
    {
        "metric_id": "acquiring_tpv_share",
        "canonical_name": "acquiring_share_of_total_payment_volume",
        "display_name": "Acquiring TPV Share",
        "description": (
            "Acquiring TPV as a percentage of total TPV "
            "for the same reported period."
        ),
        "formula": (
            "acquiring_tpv / tpv * 100"
        ),
        "unit": "percent",
        "frequency": "quarterly_reporting",
        "source": "derived from Operational Silver",
        "business_domain": "Fintech",
        "higher_is_better": None,
        "notes": (
            "Mix metric; a higher value is not automatically "
            "economically better."
        ),
    },
    {
        "metric_id": "aum_yoy_growth",
        "canonical_name": "assets_under_management_year_over_year_growth",
        "display_name": "AUM YoY Growth",
        "description": "Year-over-year growth in exact AUM observations for matching quarter-end dates.",
        "formula": "(current_value / previous_year_value - 1) * 100",
        "unit": "percent",
        "frequency": "irregular_quarterly_reporting",
        "source": "derived from Extended Operational Silver",
        "business_domain": "Fintech",
        "higher_is_better": True,
        "notes": "Exact inputs only. Published USD billions may be rounded, so derived growth can differ slightly from management's published YoY.",
    },
    {
        "metric_id": "credit_portfolio_yoy_growth",
        "canonical_name": "credit_portfolio_year_over_year_growth",
        "display_name": "Credit Portfolio YoY Growth",
        "description": "Year-over-year growth in exact total credit portfolio observations for matching quarter-end dates.",
        "formula": "(current_value / previous_year_value - 1) * 100",
        "unit": "percent",
        "frequency": "quarterly_reporting",
        "source": "derived from Extended Operational Silver",
        "business_domain": "Credit",
        "higher_is_better": None,
        "notes": "Exact inputs only; lower-bound and approximate inputs are excluded. Growth is not interpreted without credit quality context.",
    },
    {
        "metric_id": "npl_15_90_yoy_change_pp",
        "canonical_name": "total_portfolio_15_90_day_npl_year_over_year_change_pp",
        "display_name": "15-90 Day NPL YoY Change",
        "description": "Year-over-year change in total-portfolio 15-90 day NPL, expressed in percentage points.",
        "formula": "current_value - previous_year_value",
        "unit": "percentage_points",
        "frequency": "quarterly_reporting",
        "source": "derived from Extended Operational Silver",
        "business_domain": "Credit",
        "higher_is_better": False,
        "notes": "Uses total-portfolio NPL only; lower change is generally favorable. Missing total NPL is not substituted with credit-card NPL.",
    },
    {
        "metric_id": "aum_per_fintech_mau",
        "canonical_name": "assets_under_management_per_fintech_monthly_active_user",
        "display_name": "AUM per Fintech MAU",
        "description": "Exact AUM divided by reported Fintech MAU with the same period_end.",
        "formula": "aum / fintech_mau",
        "unit": "USD_per_user",
        "frequency": "irregular_quarterly_reporting",
        "source": "derived from Extended Operational Silver and Operational Silver",
        "business_domain": "Fintech",
        "higher_is_better": None,
        "notes": "Same-date snapshot ratio; not a company-reported KPI or a causal measure.",
    },
    {
        "metric_id": "credit_portfolio_per_fintech_mau",
        "canonical_name": "credit_portfolio_per_fintech_monthly_active_user",
        "display_name": "Credit Portfolio per Fintech MAU",
        "description": "Exact total credit portfolio divided by reported Fintech MAU with the same period_end.",
        "formula": "credit_portfolio / fintech_mau",
        "unit": "USD_per_user",
        "frequency": "quarterly_reporting",
        "source": "derived from Extended Operational Silver and Operational Silver",
        "business_domain": "Credit",
        "higher_is_better": None,
        "notes": "Same-date snapshot ratio; lower-bound and approximate portfolio values are excluded.",
    },
    {
        "metric_id": "selic_target_annual",
        "canonical_name": "selic_target_annual",
        "display_name": "Meta Selic",
        "description": "Annual target Selic rate defined by Copom.",
        "formula": "reported",
        "unit": "percent_per_year",
        "frequency": "daily",
        "source": "Banco Central do Brasil - SGS series 432",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Copom policy target. Distinct from the effective annualized Selic rate.",
    },
    {
        "metric_id": "selic_effective_annual_252",
        "canonical_name": "selic_effective_annual_252",
        "display_name": "Selic Efetiva Anualizada (base 252)",
        "description": (
            "Average adjusted rate of one-business-day repo operations, "
            "annualized on a 252-business-day basis."
        ),
        "formula": "reported",
        "unit": "percent_per_year",
        "frequency": "daily",
        "source": "Banco Central do Brasil - SGS series 1178",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Effective annualized rate. Distinct from Meta Selic defined by Copom.",
    },
    {
        "metric_id": "ipca_monthly_change",
        "canonical_name": "ipca_monthly_change",
        "display_name": "IPCA - Variação mensal",
        "description": "Reported monthly change of Brazil's headline IPCA.",
        "formula": "reported",
        "unit": "percent",
        "frequency": "monthly",
        "source": "IBGE - SIDRA table 1737 variable 63",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Official reported headline Brazil monthly IPCA. Distinct from the 12-month accumulated metric; the latter is not recalculated from this series.",
    },
    {
        "metric_id": "ipca_12m_change",
        "canonical_name": "ipca_12m_change",
        "display_name": "IPCA - Variação acumulada em 12 meses",
        "description": "Reported 12-month accumulated change of Brazil's headline IPCA.",
        "formula": "reported",
        "unit": "percent",
        "frequency": "monthly",
        "source": "IBGE - SIDRA table 1737 variable 2265",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Official reported headline Brazil accumulated 12-month IPCA. Distinct from the monthly metric; it is not recalculated in this pipeline.",
    },
    {
        "metric_id": "usd_brl_sell_rate",
        "canonical_name": "usd_brl_sell_rate",
        "display_name": "USD/BRL - Dólar americano venda",
        "description": "Official daily Brazilian real per US dollar selling exchange rate.",
        "formula": "reported",
        "unit": "brl_per_usd",
        "frequency": "daily",
        "source": "Banco Central do Brasil - SGS series 1",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Official BCB daily selling exchange rate; macroeconomic context only.",
    },
    {
        "metric_id": "household_free_credit_balance",
        "canonical_name": "household_free_credit_balance",
        "display_name": "Crédito livre - Pessoas físicas - Saldo total",
        "description": "Outstanding balance of free-market credit operations to individuals in Brazil.",
        "formula": "reported",
        "unit": "million_brl",
        "frequency": "monthly",
        "source": "Banco Central do Brasil - SGS series 20570",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Free-market credit only; excludes directed credit.",
    },
    {
        "metric_id": "household_free_credit_npl_90d_rate",
        "canonical_name": "household_free_credit_npl_90d_rate",
        "display_name": "Crédito livre PF - Inadimplência acima de 90 dias",
        "description": (
            "Percentage of the free-market credit portfolio to individuals "
            "with at least one installment overdue by more than 90 days."
        ),
        "formula": "reported",
        "unit": "percent",
        "frequency": "monthly",
        "source": "Banco Central do Brasil - SGS series 21112",
        "business_domain": "Macro",
        "higher_is_better": False,
        "notes": "BCB >90-day delinquency definition. Not directly comparable to MELI 15–90 day NPL metrics.",
    },
    {
        "metric_id": "unemployment_rate_rolling_3m",
        "canonical_name": "unemployment_rate_rolling_3m",
        "display_name": "Taxa de desocupação - trimestre móvel",
        "description": "Brazil unemployment rate for the three-month moving period ending in the reference month.",
        "formula": "reported",
        "unit": "percent",
        "frequency": "rolling_3m_monthly",
        "source": "IBGE - SIDRA table 6381 variable 4099",
        "business_domain": "Macro",
        "higher_is_better": False,
        "notes": "Published monthly but each observation represents a rolling three-month period ending in the reference month.",
    },
    {
        "metric_id": "ibc_br_activity_sa_index",
        "canonical_name": "ibc_br_activity_sa_index",
        "display_name": "IBC-Br com ajuste sazonal",
        "description": "Seasonally adjusted monthly Central Bank Economic Activity Index.",
        "formula": "reported",
        "unit": "index",
        "frequency": "monthly",
        "source": "Banco Central do Brasil - SGS series 24364",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Economic activity indicator; not the official GDP measure.",
    },
    {
        "metric_id": "retail_sales_volume_mom_sa",
        "canonical_name": "retail_sales_volume_mom_sa",
        "display_name": "Varejo - Volume de vendas MoM dessazonalizado",
        "description": "Seasonally adjusted month-over-month change in Brazil's retail sales volume.",
        "formula": "reported",
        "unit": "percent",
        "frequency": "monthly",
        "source": "IBGE - SIDRA table 8880 variable 11708",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": "Volume index only; excludes nominal sales revenue. Seasonally adjusted historical observations may be revised.",
    },
    {
        "metric_id": "pix_transactions_count_monthly",
        "canonical_name": "pix_transactions_count_monthly",
        "display_name": "Pix - Quantidade mensal de transações",
        "description": (
            "Monthly number of Pix transactions in Brazil according to "
            "official BCB payment-method statistics."
        ),
        "formula": "reported * 1000",
        "unit": "transactions",
        "frequency": "monthly",
        "source": "Banco Central do Brasil - Meios de Pagamentos Mensais",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": (
            "Source field quantidadePix is reported in thousands of "
            "transactions and normalized to absolute transactions. Pix "
            "monthly source combines SPI and document 1201 information."
        ),
    },
    {
        "metric_id": "pix_transactions_value_monthly",
        "canonical_name": "pix_transactions_value_monthly",
        "display_name": "Pix - Valor mensal transacionado",
        "description": (
            "Monthly financial value of Pix transactions in Brazil according "
            "to official BCB payment-method statistics."
        ),
        "formula": "reported * 1000000",
        "unit": "brl",
        "frequency": "monthly",
        "source": "Banco Central do Brasil - Meios de Pagamentos Mensais",
        "business_domain": "Macro",
        "higher_is_better": None,
        "notes": (
            "Source field valorPix is reported in millions of BRL and "
            "normalized to BRL. Historical observations may be revised."
        ),
    },
)


def validate_kpi_dictionary() -> None:
    """Validate dictionary structure and uniqueness."""
    if not KPI_DICTIONARY:
        raise ValueError(
            "KPI Dictionary cannot be empty."
        )

    metric_ids: list[str] = []

    for row in KPI_DICTIONARY:
        missing = [
            field
            for field in KPI_DICTIONARY_FIELDS
            if field not in row
        ]

        if missing:
            raise ValueError(
                "KPI Dictionary row missing fields: "
                f"{missing}"
            )

        if not row["metric_id"]:
            raise ValueError(
                "metric_id cannot be empty."
            )

        metric_ids.append(
            str(row["metric_id"])
        )

    if len(metric_ids) != len(
        set(metric_ids)
    ):
        raise ValueError(
            "KPI Dictionary metric_id values "
            "must be unique."
        )


def kpi_dictionary_frame() -> pd.DataFrame:
    """Return the validated dictionary as a DataFrame."""
    validate_kpi_dictionary()

    return pd.DataFrame(
        KPI_DICTIONARY,
        columns=KPI_DICTIONARY_FIELDS,
    )
