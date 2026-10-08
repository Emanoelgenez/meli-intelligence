"""Registry of official Banco Central do Brasil SGS series."""

from __future__ import annotations

from dataclasses import dataclass


BCB_SGS_URL_TEMPLATE = (
    "https://api.bcb.gov.br/dados/serie/"
    "bcdata.sgs.{sgs_code}/dados"
)


@dataclass(frozen=True)
class BCBSeries:
    metric_id: str
    sgs_code: int
    display_name: str
    description: str
    unit: str
    frequency: str
    business_domain: str
    source: str
    source_url_template: str = BCB_SGS_URL_TEMPLATE

    def source_url(self) -> str:
        """Return the deterministic SGS endpoint for this series."""
        return self.source_url_template.format(sgs_code=self.sgs_code)

    @property
    def source_series_id(self) -> str:
        """Return a source-qualified identifier for shared macro Silver."""
        return f"bcb_sgs:{self.sgs_code}"


BCB_SERIES: dict[int, BCBSeries] = {
    1: BCBSeries(
        metric_id="usd_brl_sell_rate",
        sgs_code=1,
        display_name="USD/BRL - Dólar americano venda",
        description=(
            "Official daily Brazilian real per US dollar selling exchange rate "
            "published by Banco Central do Brasil."
        ),
        unit="brl_per_usd",
        frequency="daily",
        business_domain="Macro",
        source="Banco Central do Brasil - SGS",
    ),
    432: BCBSeries(
        metric_id="selic_target_annual",
        sgs_code=432,
        display_name="Meta Selic definida pelo Copom",
        description="Annual target Selic rate defined by Copom.",
        unit="percent_per_year",
        frequency="daily",
        business_domain="Macro",
        source="Banco Central do Brasil - SGS",
    ),
    1178: BCBSeries(
        metric_id="selic_effective_annual_252",
        sgs_code=1178,
        display_name="Selic anualizada base 252",
        description=(
            "Average adjusted rate of one-business-day repo operations, "
            "annualized on a 252-business-day basis."
        ),
        unit="percent_per_year",
        frequency="daily",
        business_domain="Macro",
        source="Banco Central do Brasil - SGS",
    ),
    20570: BCBSeries(
        metric_id="household_free_credit_balance",
        sgs_code=20570,
        display_name="Crédito livre - Pessoas físicas - Saldo total",
        description=(
            "Outstanding balance of free-market credit operations to "
            "individuals in Brazil."
        ),
        unit="million_brl",
        frequency="monthly",
        business_domain="Macro",
        source="Banco Central do Brasil - SGS",
    ),
    21112: BCBSeries(
        metric_id="household_free_credit_npl_90d_rate",
        sgs_code=21112,
        display_name="Crédito livre PF - Inadimplência acima de 90 dias",
        description=(
            "Percentage of the free-market credit portfolio to individuals "
            "with at least one installment overdue by more than 90 days."
        ),
        unit="percent",
        frequency="monthly",
        business_domain="Macro",
        source="Banco Central do Brasil - SGS",
    ),
    24364: BCBSeries(
        metric_id="ibc_br_activity_sa_index",
        sgs_code=24364,
        display_name="Índice de Atividade Econômica do Banco Central (IBC-Br) com ajuste sazonal",
        description="Seasonally adjusted monthly Central Bank Economic Activity Index for Brazil.",
        unit="index",
        frequency="monthly",
        business_domain="Macro",
        source="Banco Central do Brasil - SGS",
    ),
}


SERIES_BY_METRIC_ID = {
    series.metric_id: series
    for series in BCB_SERIES.values()
}


def get_bcb_series(series_code: int) -> BCBSeries:
    """Return a registered series or fail with an explicit message."""
    try:
        return BCB_SERIES[series_code]
    except KeyError as exc:
        raise ValueError(f"Unregistered BCB SGS series: {series_code}") from exc
