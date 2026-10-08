"""Registry of the two monthly Pix aggregates from BCB payment methods."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PixSeries:
    metric_id: str
    source_series_id: str
    display_name: str
    description: str
    source_field: str
    source_unit: str
    silver_unit: str
    scale_factor: int
    frequency: str = "monthly"
    business_domain: str = "Macro"
    higher_is_better: bool | None = None
    source: str = "Banco Central do Brasil - Meios de Pagamentos Mensais"


PIX_SERIES: tuple[PixSeries, ...] = (
    PixSeries(
        metric_id="pix_transactions_count_monthly",
        source_series_id="bcb_mpv:monthly:quantidadePix",
        display_name="Pix - Quantidade mensal de transações",
        description=(
            "Monthly number of Pix transactions in Brazil according to the "
            "official BCB monthly payment-method statistics."
        ),
        source_field="quantidadePix",
        source_unit="thousand_transactions",
        silver_unit="transactions",
        scale_factor=1_000,
    ),
    PixSeries(
        metric_id="pix_transactions_value_monthly",
        source_series_id="bcb_mpv:monthly:valorPix",
        display_name="Pix - Valor mensal transacionado",
        description=(
            "Monthly financial value of Pix transactions in Brazil according "
            "to the official BCB monthly payment-method statistics."
        ),
        source_field="valorPix",
        source_unit="million_brl",
        silver_unit="brl",
        scale_factor=1_000_000,
    ),
)

PIX_SERIES_BY_ID = {series.metric_id: series for series in PIX_SERIES}


def get_pix_series(metric_id: str) -> PixSeries:
    """Return a registered monthly Pix metric."""
    try:
        return PIX_SERIES_BY_ID[metric_id]
    except KeyError as exc:
        raise ValueError(f"Unregistered BCB Pix metric: {metric_id}") from exc
