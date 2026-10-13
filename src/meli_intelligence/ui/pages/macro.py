"""Macro context page using existing normalized and derived datasets."""

from __future__ import annotations

import json

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.macro_storytelling import (
    MACRO_ADDITIONAL,
    MACRO_PRIORITY,
    MACRO_TREND_METRICS,
    macro_freshness,
    select_macro_observations,
    select_macro_snapshots,
    select_macro_trend,
)
from meli_intelligence.ui.presentation import (
    format_date_br,
    format_status,
    select_latest_interpretations,
)

DATASET_IDS = (
    "macro_indicators",
    "macro_analytics",
    "macro_evidence",
    "interpretations",
)


def _load(health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    health_by_id = {item.dataset_id: item for item in health_records}
    frames: dict[str, pd.DataFrame | None] = {}
    failures = []
    for dataset_id in DATASET_IDS:
        item = health_by_id.get(dataset_id)
        if item is None or item.status != "AVAILABLE":
            frames[dataset_id] = None
            continue
        try:
            frames[dataset_id] = load_dataset(
                dataset_id, path=item.path, filters=filters
            )
        except Exception as exc:
            frames[dataset_id] = None
            failures.append(f"{dataset_id}: {type(exc).__name__}")
    statuses = tuple(
        f"{dataset_id}: {format_status(health_by_id[dataset_id].status)}"
        for dataset_id in DATASET_IDS
        if dataset_id in health_by_id and health_by_id[dataset_id].status != "AVAILABLE"
    )
    statuses += tuple(
        f"{dataset_id}: indisponível — conjunto não cadastrado"
        for dataset_id in DATASET_IDS
        if dataset_id not in health_by_id
    )
    return frames, statuses, failures


def _format_frequency(value: str) -> str:
    labels = {
        "daily": "Diária",
        "monthly": "Mensal",
        "rolling_3m_monthly": "Publicação mensal · taxa móvel de três meses",
    }
    return labels.get(
        value,
        value.replace("_", " ").capitalize() if value else "Frequência não informada",
    )


def _lineage_values(row, column: str) -> list[str]:
    value = row.get(column)
    if value is None or pd.isna(value):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return list(map(str, parsed)) if isinstance(parsed, list) else [str(parsed)]
    return list(map(str, value))


def render(
    st, health_records, catalog=None, filters: FilterState | None = None
) -> None:
    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date)
    frames, degraded, failures = _load(health_records, date_filters)
    st.title("Cenário macroeconômico")
    st.caption(
        "O que o cenário macroeconômico brasileiro mostra sobre o contexto "
        "operacional do Mercado Livre?"
    )

    latest = macro_freshness(frames, filters=date_filters)
    st.caption(f"Data de referência mais recente: {format_date_br(latest)}")
    if degraded:
        st.warning(
            "Disponibilidade de dados macroeconômicos limitada: "
            + "; ".join(degraded)
            + "."
        )
    if failures:
        st.warning(
            "Não foi possível ler alguns conjuntos macroeconômicos: "
            + "; ".join(failures)
            + "."
        )

    st.subheader("Principais indicadores macroeconômicos")
    priority_ids = tuple(spec.metric_id for spec in MACRO_PRIORITY)
    snapshots = select_macro_snapshots(
        frames, filters=date_filters, metric_ids=priority_ids
    )
    if snapshots:
        columns = st.columns(min(4, len(snapshots)))
        for column, snapshot in zip(columns, snapshots):
            with column:
                st.metric(snapshot.display_name, snapshot.formatted_value)
                st.caption(
                    f"{_format_frequency(snapshot.frequency)} · Data de referência: "
                    f"{format_date_br(snapshot.reference_date)}"
                )
                st.caption(snapshot.context)
                with st.expander("Fonte e precisão reportada"):
                    st.write(f"Fonte: {snapshot.source}")
                    st.write(
                        f"Valor conforme carregado: {snapshot.full_precision_value}"
                    )
                    if snapshot.source_url:
                        st.write(f"URL da fonte: {snapshot.source_url}")
    else:
        st.info(
            "Não há indicadores macroeconômicos prioritários neste período. "
            "Valores ausentes não são substituídos por zero."
        )
    available_primary = {item.metric_id for item in snapshots}
    missing_primary = [
        spec.label for spec in MACRO_PRIORITY if spec.metric_id not in available_primary
    ]
    if missing_primary:
        st.caption(
            "Indicadores prioritários indisponíveis neste período: "
            + ", ".join(missing_primary)
            + "."
        )

    trend_id = next(iter(MACRO_TREND_METRICS))
    trend_spec = next(spec for spec in MACRO_PRIORITY if spec.metric_id == trend_id)
    trend = select_macro_trend(frames, metric_id=trend_id, filters=date_filters)
    st.subheader("Meta da taxa Selic · observações diárias reportadas")
    if trend.empty:
        st.info(f"Não há observações reportadas de {trend_spec.label} neste período.")
    else:
        st.caption(
            "Meta da Selic · observações diárias reportadas. As datas originais são "
            "mantidas; sem reamostragem, interpolação ou cálculo de variação."
        )
        st.line_chart(
            trend,
            x="reference_date",
            y="value",
            x_label="Data de referência",
            y_label=trend_spec.label,
        )

    st.subheader("Observações macroeconômicas existentes")
    observations = select_macro_observations(
        frames.get("macro_evidence"), filters=date_filters
    )
    if observations.empty:
        st.info("Não há observações macroeconômicas salvas para o período selecionado.")
    else:
        for _, row in observations.iterrows():
            st.markdown(f"**Observação · {MACRO_LABEL_FOR(str(row.metric_id))}**")
            st.write(str(row.claim))
            st.caption(
                f"{row.source} · {format_date_br(row.reference_date)} · "
                f"ID da evidência: {row.evidence_id}"
            )

    interpretation_frame = frames.get("interpretations")
    if (
        interpretation_frame is not None
        and "business_domain" in interpretation_frame.columns
    ):
        interpretation_frame = interpretation_frame.loc[
            interpretation_frame.business_domain.astype(str) == "Macro"
        ].copy()
    interpretations = select_latest_interpretations(
        interpretation_frame, filters=date_filters, limit=3
    )
    st.subheader("Interpretações existentes")
    if not interpretations:
        st.info("Não há interpretação macroeconômica salva para o período selecionado.")
    else:
        for item in interpretations:
            st.markdown(f"**Interpretação · {MACRO_LABEL_FOR(item.metric_id)}**")
            st.write(item.claim)
            st.caption(
                f"{item.source} · {format_date_br(item.reference_date)} · "
                f"ID da evidência: {item.evidence_id}"
            )

    with st.expander("Contexto macroeconômico adicional"):
        extra_ids = tuple(spec.metric_id for spec in MACRO_ADDITIONAL)
        additional = select_macro_snapshots(
            frames,
            filters=date_filters,
            metric_ids=extra_ids,
            limit=len(MACRO_ADDITIONAL),
        )
        if not additional:
            st.info(
                "Não há outros dados ou análises macroeconômicas salvos "
                "para este período."
            )
        else:
            table = pd.DataFrame(
                [
                    {
                        "Indicador": row.display_name,
                        "Valor reportado": row.formatted_value,
                        "Frequência": _format_frequency(row.frequency),
                        "Data de referência": format_date_br(row.reference_date),
                        "Fonte": row.source,
                    }
                    for row in additional
                ]
            )
            st.dataframe(table, width="stretch", hide_index=True)
            st.caption(
                "Os valores derivados vêm das análises macroeconômicas Gold já salvas; "
                "a interface não os recalcula."
            )

    with st.expander("Metodologia e limites"):
        st.write(
            "Os dados Silver são a fonte dos indicadores reportados. As análises Gold "
            "aparecem somente quando já estão salvas. Frequências diárias, "
            "mensais e móveis de três meses permanecem distintas."
        )
        st.write(
            "O IBC-Br é um indicador de atividade, não o PIB. O desemprego usa uma "
            "publicação móvel de três meses com janelas sobrepostas. A "
            "inadimplência das famílias acima de 90 dias do Banco Central difere "
            "da medida MELI de 15 a 90 dias."
        )
        st.write(
            "Os indicadores macroeconômicos descrevem o contexto; esta página não "
            "apresenta conclusões causais nem recomendações de produto."
        )
    st.caption("Os filtros usam datas de referência econômica, não horários de coleta.")


def MACRO_LABEL_FOR(metric_id: str) -> str:
    from meli_intelligence.ui.macro_storytelling import MACRO_LABELS

    return MACRO_LABELS.get(metric_id, "Indicador macroeconômico")
