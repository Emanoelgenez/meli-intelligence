"""Read-only Financial facts storytelling page."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.financial_storytelling import (
    FINANCIAL_QUESTION,
    financial_freshness,
    financial_metric_availability,
    financial_metric_label,
    financial_period_description,
    select_financial_context,
    select_financial_interpretations,
    select_financial_snapshots,
    select_financial_trend,
    select_financial_yoy,
)
from meli_intelligence.ui.presentation import (
    format_date_br,
    format_metric,
    format_period_label,
    format_status,
)
from meli_intelligence.ui.temporal_charts import (
    chart_frame,
    chart_history,
    quarterly_chart_spec,
)

DATASET_IDS = ("financial_facts", "interpretations")


def _load(health_records, filters: FilterState):
    from meli_intelligence.ui.data import load_dataset

    health_by_id = {item.dataset_id: item for item in health_records}
    frames: dict[str, pd.DataFrame | None] = {}
    degraded, failures = [], []
    for dataset_id in DATASET_IDS:
        item = health_by_id.get(dataset_id)
        if item is None or item.status != "AVAILABLE":
            frames[dataset_id] = None
            if dataset_id == "financial_facts":
                degraded.append(
                    "Dados financeiros: "
                    + format_status(item.status if item else "MISSING")
                )
            continue
        try:
            frames[dataset_id] = load_dataset(
                dataset_id, path=item.path
            )
        except Exception as exc:
            frames[dataset_id] = None
            label = (
                "dados financeiros"
                if dataset_id == "financial_facts"
                else "interpretações registradas"
            )
            failures.append(f"{label}: {type(exc).__name__}")
    return frames, degraded, failures


def render(
    st, health_records, catalog=None, filters: FilterState | None = None
) -> None:
    state = (filters or FilterState()).validate()
    frames, degraded, failures = _load(health_records, state)
    facts = frames.get("financial_facts")
    st.title("Financeiro")
    st.caption(FINANCIAL_QUESTION)
    st.caption(
        f"Data econômica mais recente: "
        f"{format_date_br(financial_freshness(facts, filters=state))}"
    )
    if degraded:
        st.warning(
            "Disponibilidade de dados financeiros limitada: "
            + "; ".join(degraded)
            + ". Consulte Fontes e qualidade dos dados."
        )
    if failures:
        st.warning(
            "Não foi possível ler alguns conjuntos de dados desta página: "
            + "; ".join(failures)
            + "."
        )

    st.subheader("Principais dados financeiros reportados")
    snapshots = select_financial_snapshots(facts, filters=state)
    if snapshots:
        columns = st.columns(min(len(snapshots), 4))
        for column, fact in zip(columns, snapshots):
            with column:
                st.metric(fact.display_name, fact.formatted_value)
                st.caption(financial_period_description(fact))
                st.caption(fact.context)
                with st.expander("Fonte e precisão reportada"):
                    st.write(f"Unidade: {fact.unit or 'não informada'}")
                    st.write(f"Fonte: {fact.source}")
                    st.write(
                        f"Data de protocolo: {format_date_br(fact.filing_date)} "
                        "· Formulário: "
                        f"{fact.form or 'não informado'}"
                    )
                    st.write(
                        f"Número de acesso: {fact.accession_number or 'não informado'}"
                    )
                    st.write(f"Valor conforme carregado: {fact.full_precision_value}")
    else:
        st.info(
            "Não há dados financeiros trimestrais disponíveis neste período. "
            "Valores ausentes não são substituídos por zero."
        )
    missing = financial_metric_availability(facts, filters=state)
    if missing:
        st.caption(
            "Indicadores prioritários indisponíveis neste período: "
            + ", ".join(missing)
            + "."
        )

    st.subheader("Receita trimestral reportada")
    trend = select_financial_trend(facts, filters=state)
    if trend.empty:
        st.info(
            "Não há série trimestral comparável de receita para o período selecionado."
        )
    else:
        st.caption(
            "Dados de duração trimestral, exibidos nas datas reportadas. "
            "Não há preenchimento, reamostragem ou recálculo de períodos."
        )
        full_history = st.checkbox(
            "Exibir todo o histórico", key="historico_financeiro"
        )
        visible_trend = chart_history(trend, full_history=full_history)
        unit = str(trend.get("unit", pd.Series(["USD"])).iloc[0])
        chart = chart_frame(
            visible_trend,
            "period_end",
            "Receita e resultado financeiro reportados",
            unit=unit,
            definition="Receita e resultado financeiro reportados no trimestre.",
        )
        st.vega_lite_chart(
            chart,
            quarterly_chart_spec(
                chart,
                "period_end",
                "Receita e resultado financeiro reportados",
                unit=unit,
                definition="Receita e resultado financeiro reportados no trimestre.",
            ),
            width="stretch",
        )

    st.subheader("O que os dados mostram")
    st.markdown("**Fato observado**")
    revenue = next(
        (
            item
            for item in snapshots
            if item.metric_id == "net_revenues_financial_income"
        ),
        None,
    )
    if revenue is None:
        st.write(
            "Não há observação trimestral de receita para os filtros selecionados."
        )
    else:
        st.write(
            f"A receita e o resultado financeiro reportados foram "
            f"{revenue.formatted_value} em {revenue.period_label}."
        )

    st.markdown("**Comparação anual**")
    comparison = select_financial_yoy(facts, filters=state)
    if comparison is None:
        period = revenue.period_label if revenue else "o período selecionado"
        st.write(
            "Não há dados suficientes para estabelecer uma comparação anual "
            f"válida para receita em {period}."
        )
    else:
        period = format_period_label("QUARTER", comparison[0])
        st.write(
            f"A receita e o resultado financeiro variaram "
            f"{format_metric(comparison[1], 'percent')} em relação ao mesmo "
            f"trimestre do ano anterior ({period})."
        )
    st.markdown("**Limitações**")
    st.caption(
        "A comparação usa apenas observações trimestrais com período econômico "
        "equivalente e unidade compatível. Ausências não são estimadas."
    )

    interpretations = select_financial_interpretations(
        frames.get("interpretations"), filters=state
    )
    if interpretations:
        st.subheader("Interpretações registradas")
        for item in interpretations:
            st.markdown(f"**Interpretação · {financial_metric_label(item.metric_id)}**")
            st.write(item.claim)
            st.caption(
                f"{item.source} · {format_date_br(item.reference_date)} · "
                f"ID da evidência: {item.evidence_id}"
            )

    with st.expander("Rentabilidade, geração de caixa e posição patrimonial"):
        context = select_financial_context(facts, filters=state)
        if not context:
            st.info("Não há dados de apoio disponíveis para este período.")
        else:
            detail = pd.DataFrame(
                [
                    {
                        "Indicador": fact.display_name,
                        "Valor reportado": fact.formatted_value,
                        "Período": financial_period_description(fact),
                        "Data de protocolo": format_date_br(fact.filing_date),
                        "Fonte": fact.source,
                    }
                    for fact in context
                ]
            )
            st.dataframe(detail, width="stretch", hide_index=True)
    with st.expander("Metodologia e limites"):
        st.write(
            "Esta página apresenta somente dados normalizados do SEC Company Facts. "
            "A data final indica o período econômico; a data de protocolo e o "
            "número de acesso identificam o contexto do documento."
        )
        st.write(
            "Dados trimestrais, acumulados no ano, anuais e instantâneos não são "
            "combinados. A interface não calcula crescimento, margens, índices "
            "de caixa nem conversões entre períodos."
        )
        st.write(
            "Os fundamentos da empresa são distintos de preços de mercado e "
            "avaliação. Dados financeiros não demonstram comportamento de "
            "usuários, resultados de produto ou causalidade."
        )
    st.caption(
        "Os filtros de data usam o fim do período econômico. A data de protocolo "
        "não substitui a data de referência econômica."
    )
