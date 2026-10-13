"""Dataset health, paths, and existing source lineage visibility."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.data import load_dataset
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.presentation import (
    display_domain,
    format_date_br,
    format_status,
)

_LINEAGE_COLUMNS = (
    "source",
    "source_url",
    "metric_id",
    "source_metric_id",
    "source_series_id",
    "source_evidence_ids",
    "source_pestel_ids",
    "source_swot_ids",
    "source_hypothesis_ids",
    "source_bronze_file",
    "retrieved_at",
    "filed_at",
    "accession_number",
)
_DATASET_NAMES = {
    "financial_facts": "Dados financeiros",
    "operational_kpis": "Indicadores operacionais",
    "extended_operational_kpis": "Indicadores operacionais estendidos",
    "extended_operational_evidence": "Evidências operacionais estendidas",
    "macro_indicators": "Indicadores macroeconômicos",
    "macro_analytics": "Análises macroeconômicas",
    "macro_evidence": "Observações macroeconômicas",
    "evidence_registry": "Registro de evidências",
    "interpretations": "Interpretações",
    "pestel": "Classificações PESTEL",
    "swot": "Classificações SWOT",
    "product_evidence": "Evidências de produto",
    "market_prices": "Preços de mercado",
    "market_capitalization": "Capitalização de mercado",
}


def health_rows(health_records, catalog) -> pd.DataFrame:
    specs = {spec.dataset_id: spec for spec in catalog}
    records = []
    for item in health_records:
        spec = specs[item.dataset_id]
        records.append(
            {
                "ID do conjunto": item.dataset_id,
                "Nome": _DATASET_NAMES.get(item.dataset_id, spec.display_name),
                "Camada": f"Camada {spec.layer}",
                "Área de negócio": ", ".join(
                    display_domain(domain) for domain in spec.business_domains
                )
                or "—",
                "Disponibilidade": format_status(item.status),
                "Linhas": item.row_count,
                "Colunas": item.column_count,
                "Data de referência mais recente": format_date_br(
                    item.latest_reference_date
                ),
                "message": item.message,
            }
        )
    return pd.DataFrame(records)


def source_preview(
    dataset_id: str,
    *,
    path=None,
    limit: int = 5,
    filters: FilterState | None = None,
) -> pd.DataFrame:
    frame = load_dataset(dataset_id, path=path, filters=filters)
    columns = [column for column in _LINEAGE_COLUMNS if column in frame.columns]
    if not columns:
        return pd.DataFrame(
            {"message": ["Não há colunas de fonte ou linhagem neste conjunto."]}
        )
    return frame.loc[:, columns].head(limit).copy()


def render(st, health_records, catalog, filters: FilterState | None = None) -> None:
    st.title("Fontes e qualidade dos dados")
    st.caption(
        "Disponibilidade, atualização e linhagem vêm dos conjuntos locais e "
        "dos metadados das fontes."
    )
    rows = health_rows(health_records, catalog)
    state = (filters or FilterState()).validate()
    if state.business_domain is not None:
        selected = {
            spec.dataset_id
            for spec in catalog
            if state.business_domain in spec.business_domains
        }
        rows = rows.loc[rows["ID do conjunto"].isin(selected)].reset_index(drop=True)
    st.dataframe(
        rows.drop(columns=["message"], errors="ignore"),
        width="stretch",
        hide_index=True,
    )
    for item in health_records:
        if state.business_domain is not None:
            spec = next(spec for spec in catalog if spec.dataset_id == item.dataset_id)
            if state.business_domain not in spec.business_domains:
                continue
        if item.status != "AVAILABLE":
            with st.expander(f"{item.dataset_id} — {format_status(item.status)}"):
                st.write(
                    {
                        "MISSING": "Arquivo local não encontrado.",
                        "EMPTY": "Arquivo legível, sem observações.",
                        "INVALID": "Arquivo inválido ou sem permissão de leitura.",
                    }.get(item.status, "Indisponível — motivo não informado.")
                )
                st.caption(f"Caminho: {item.path}")
            continue
        with st.expander(f"Detalhes e campos de origem — {item.dataset_id}"):
            st.caption(f"{format_status(item.status)} · Caminho: {item.path}")
            st.write("Conjunto disponível para leitura.")
            try:
                preview = source_preview(
                    item.dataset_id, path=item.path, filters=filters
                )
                st.dataframe(preview, width="stretch", hide_index=True)
            except Exception as exc:
                st.info(f"Prévia da linhagem indisponível ({type(exc).__name__}).")
