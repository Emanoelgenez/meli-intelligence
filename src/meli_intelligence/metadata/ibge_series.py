"""Registry of headline Brazil IPCA series published by IBGE/SIDRA."""

from __future__ import annotations

from dataclasses import dataclass


SIDRA_URL_TEMPLATE = (
    "https://apisidra.ibge.gov.br/values/t/{table_id}/n1/all/"
    "v/{variable_id}/p/all"
)


@dataclass(frozen=True)
class SIDRAClassificationFilter:
    """One SIDRA classification selection with request IDs and semantic labels."""

    classification_id: int
    category_id: int
    dimension_name: str
    category_name: str


@dataclass(frozen=True)
class IBGESeries:
    metric_id: str
    table_id: int
    variable_id: int
    display_name: str
    description: str
    unit: str
    frequency: str
    business_domain: str
    source: str
    territorial_level: str
    territory: str
    source_url_template: str = SIDRA_URL_TEMPLATE
    classification_filters: tuple[SIDRAClassificationFilter, ...] = ()
    source_series_id_override: str | None = None

    @property
    def source_series_id(self) -> str:
        return self.source_series_id_override or f"ibge_sidra:{self.table_id}:{self.variable_id}"

    def source_url(
        self,
        *,
        classification_filters: tuple[SIDRAClassificationFilter, ...] | None = None,
    ) -> str:
        filters = self.classification_filters if classification_filters is None else classification_filters
        url = self.source_url_template.format(
            table_id=self.table_id, variable_id=self.variable_id
        )
        for selection in filters:
            url += f"/c{selection.classification_id}/{selection.category_id}"
        return url


IBGE_SERIES: dict[tuple[int, int], IBGESeries] = {
    (1737, 63): IBGESeries(
        metric_id="ipca_monthly_change", table_id=1737, variable_id=63,
        display_name="IPCA - Variação mensal",
        description="Reported monthly change of Brazil's headline IPCA.",
        unit="percent", frequency="monthly", business_domain="Macro",
        source="IBGE - SIDRA", territorial_level="n1", territory="Brasil",
    ),
    (1737, 2265): IBGESeries(
        metric_id="ipca_12m_change", table_id=1737, variable_id=2265,
        display_name="IPCA - Variação acumulada em 12 meses",
        description=("Reported 12-month accumulated change of Brazil's headline IPCA."),
        unit="percent", frequency="monthly", business_domain="Macro",
        source="IBGE - SIDRA", territorial_level="n1", territory="Brasil",
    ),
    (6381, 4099): IBGESeries(
        metric_id="unemployment_rate_rolling_3m", table_id=6381, variable_id=4099,
        display_name="Taxa de desocupação, na semana de referência, das pessoas de 14 anos ou mais de idade",
        description="Brazil unemployment rate for the three-month moving period ending in the reference month.",
        unit="percent", frequency="rolling_3m_monthly", business_domain="Macro",
        source="IBGE - SIDRA", territorial_level="n1", territory="Brasil",
    ),
    (8880, 11708): IBGESeries(
        metric_id="retail_sales_volume_mom_sa", table_id=8880, variable_id=11708,
        display_name="PMC - Variação mês/mês imediatamente anterior, com ajuste sazonal (M/M-1)",
        description="Seasonally adjusted month-over-month change in Brazil's retail sales volume.",
        unit="percent", frequency="monthly", business_domain="Macro",
        source="IBGE - SIDRA", territorial_level="n1", territory="Brasil",
        classification_filters=(
            SIDRAClassificationFilter(
                classification_id=11046,
                category_id=56734,
                dimension_name="Tipos de índice",
                category_name="Índice de volume de vendas no comércio varejista",
            ),
        ),
        source_series_id_override="ibge_sidra:8880:11708:retail_volume",
    ),
}


def get_ibge_series(table_id: int, variable_id: int) -> IBGESeries:
    try:
        return IBGE_SERIES[(table_id, variable_id)]
    except KeyError as exc:
        raise ValueError(
            f"Unregistered IBGE SIDRA series: table={table_id}, variable={variable_id}"
        ) from exc
