"""Executive overview renderer; presentation only, with no business calculations."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.ui.data import load_dataset
from meli_intelligence.ui.domain_storytelling import (
    domain_freshness,
    select_domain_trend,
    select_domain_yoy,
)
from meli_intelligence.ui.filters import FilterState
from meli_intelligence.ui.financial_storytelling import (
    financial_freshness,
    select_financial_trend,
    select_financial_yoy,
)
from meli_intelligence.ui.presentation import (
    display_domain,
    format_date_br,
    format_metric,
    format_period_label,
    format_status,
    select_executive_signals,
    select_latest_interpretations,
)
from meli_intelligence.ui.public_demo import public_demo_enabled
from meli_intelligence.ui.storytelling import CENTRAL_QUESTION, availability_frame
from meli_intelligence.ui.temporal_charts import (
    chart_frame,
    chart_history,
    quarterly_chart_spec,
    render_series_coverage,
)

_OVERVIEW_DATASETS = frozenset(
    {
        "financial_facts",
        "operational_kpis",
        "macro_indicators",
        "interpretations",
    }
)
_MARKET_REFERENCE_DATASETS = frozenset({"market_prices", "market_capitalization"})
_MACRO_REFERENCE_DATASETS = frozenset({"macro_indicators"})


def _latest_reference_date(health_records, dataset_ids: frozenset[str]):
    dates = [
        item.latest_reference_date
        for item in health_records
        if item.dataset_id in dataset_ids and item.latest_reference_date is not None
    ]
    return max(dates) if dates else None


def _reference_label(value, missing_reason: str) -> str:
    return (
        format_date_br(value)
        if value is not None
        else f"Indisponível — {missing_reason}"
    )


def availability_by_domain_layer(health_records, catalog) -> pd.DataFrame:
    """Keep the Sprint 5A dataframe contract while delegating aggregation."""
    frame = availability_frame(health_records, catalog)
    if frame.empty:
        return pd.DataFrame(
            columns=["business_domain", "layer", "datasets", "available"]
        )

    status_codes = {
        format_status("AVAILABLE"): "AVAILABLE",
        format_status("MISSING"): "MISSING",
        format_status("EMPTY"): "EMPTY",
        format_status("INVALID"): "INVALID",
    }
    return (
        frame.assign(status=frame["status"].map(status_codes))
        .rename(columns={"dataset_count": "datasets"})
        .loc[:, ["business_domain", "layer", "status", "datasets"]]
        .sort_values(["business_domain", "layer", "status"], kind="mergesort")
        .reset_index(drop=True)
    )


def _available_frames(health_records, filters: FilterState) -> tuple[dict, list[str]]:
    frames = {}
    errors = []
    for health in health_records:
        if health.status != "AVAILABLE" or health.dataset_id not in _OVERVIEW_DATASETS:
            continue
        try:
            load_filters = (
                FilterState()
                if health.dataset_id in {"financial_facts", "operational_kpis"}
                else filters
            )
            frames[health.dataset_id] = load_dataset(
                health.dataset_id, path=health.path, filters=load_filters
            )
        except Exception as exc:
            errors.append(f"{health.dataset_id}: {type(exc).__name__}")
    return frames, errors


def render(st, health_records, catalog, filters: FilterState | None = None) -> None:
    state = (filters or FilterState()).validate()
    st.title("Visão geral")
    st.caption("Painel de indicadores reportados do Mercado Livre.")
    st.markdown(f"**Pergunta executiva:** {CENTRAL_QUESTION}")

    frames, read_errors = _available_frames(health_records, state)
    signals = select_executive_signals(frames, filters=state)
    signals_by_domain = {signal.business_domain: signal for signal in signals}
    story_domains = tuple(
        domain
        for domain in ("Financial", "Commerce", "Fintech")
        if state.business_domain is None or state.business_domain == domain
    )
    financial_reference = _reference_label(
        financial_freshness(frames.get("financial_facts"), filters=state)
        or (
            _latest_reference_date(health_records, frozenset({"financial_facts"}))
            if state.start_date is None and state.end_date is None
            else None
        ),
        "sem observação financeira nos filtros",
    )
    commerce_reference = _reference_label(
        domain_freshness(frames, "Commerce", filters=state)
        or (
            _latest_reference_date(health_records, frozenset({"operational_kpis"}))
            if state.start_date is None and state.end_date is None
            else None
        ),
        "sem observação de Comércio nos filtros",
    )
    fintech_reference = _reference_label(
        domain_freshness(frames, "Fintech", filters=state)
        or (
            _latest_reference_date(health_records, frozenset({"operational_kpis"}))
            if state.start_date is None and state.end_date is None
            else None
        ),
        "sem observação de Serviços financeiros nos filtros",
    )
    macro_reference = _reference_label(
        _latest_reference_date(health_records, _MACRO_REFERENCE_DATASETS),
        "sem dados macroeconômicos válidos",
    )
    market_reference = (
        "Indisponível — não incluído nesta demonstração"
        if public_demo_enabled()
        else _reference_label(
            _latest_reference_date(health_records, _MARKET_REFERENCE_DATASETS),
            "sem observação de mercado",
        )
    )
    top = st.columns(5)
    top[0].markdown(f"**Financeiro**  \n{financial_reference}")
    top[1].markdown(f"**Comércio**  \n{commerce_reference}")
    top[2].markdown(f"**Serviços financeiros**  \n{fintech_reference}")
    top[3].markdown(f"**Indicadores macroeconômicos**  \n{macro_reference}")
    top[4].markdown(f"**Atualização de mercado**  \n{market_reference}")
    if read_errors:
        st.info(
            "Alguns dados não puderam ser carregados. Consulte Fontes e "
            "qualidade dos dados para ver os detalhes."
        )

    st.subheader("Indicadores principais")
    if signals:
        columns = st.columns(min(len(signals), 4))
        for column, signal in zip(columns, signals):
            with column:
                st.markdown(f"**{display_domain(signal.business_domain)}**")
                st.metric(signal.display_name, signal.formatted_value)
                st.caption(
                    f"{signal.period_label} · Data de referência: "
                    f"{format_date_br(signal.reference_date)}"
                )
                st.caption(signal.context)
                with st.expander("Fonte e precisão reportada"):
                    st.write(f"Fonte: {signal.source}")
                    st.write(f"Identificador da métrica: {signal.metric_id}")
                    st.write(f"Valor conforme carregado: {signal.full_precision_value}")
        represented = {signal.business_domain for signal in signals}
        missing_domains = [
            display_domain(domain)
            for domain in story_domains
            if domain not in represented
        ]
        if missing_domains:
            st.caption(
                "Indicadores indisponíveis para: " + ", ".join(missing_domains) + "."
            )
    else:
        st.info(
            "Não há indicadores para os filtros selecionados. "
            "Valores ausentes não são substituídos por zero."
        )

    st.subheader("Evolução histórica")
    trend_specs = {
        "Financial": (
            select_financial_trend(frames.get("financial_facts"), filters=state),
            "period_end",
            "Receita e resultado financeiro",
        ),
        "Commerce": (
            select_domain_trend(frames, "Commerce", filters=state),
            "reference_date",
            "Volume bruto de mercadorias (GMV)",
        ),
        "Fintech": (
            select_domain_trend(frames, "Fintech", filters=state),
            "reference_date",
            "Volume total de pagamentos (TPV)",
        ),
    }
    visible_trend_specs = [(domain, *trend_specs[domain]) for domain in story_domains]
    if not visible_trend_specs:
        st.info(
            "A Visão geral reúne Financeiro, Comércio e Serviços financeiros. "
            "Selecione uma dessas áreas para ver sua evolução."
        )
    for column, (domain, trend, date_column, label) in zip(
        st.columns(max(len(visible_trend_specs), 1)),
        visible_trend_specs,
        strict=False,
    ):
        with column:
            st.markdown(f"**{display_domain(domain)}**")
            if trend.empty:
                st.info(f"Não há série trimestral disponível de {label}.")
                continue
            full_series = (
                select_financial_trend(frames.get("financial_facts"))
                if domain == "Financial"
                else select_domain_trend(
                    frames, domain, metric_id=("gmv" if domain == "Commerce" else "tpv")
                )
            )
            render_series_coverage(st, trend, date_column, full_series=full_series)
            full_history = st.checkbox(
                "Exibir todo o histórico", key=f"historico_visao_{domain}"
            )
            visible = chart_history(trend, full_history=full_history)
            unit = str(visible.get("unit", pd.Series(["USD"])).iloc[0])
            chart = chart_frame(
                visible, date_column, label, unit=unit, definition=label
            )
            st.vega_lite_chart(
                chart,
                quarterly_chart_spec(
                    chart, date_column, label, unit=unit, definition=label
                ),
                width="stretch",
            )

    st.subheader("O que os dados mostram")
    st.markdown("**Fatos observados**")
    for domain in story_domains:
        signal = signals_by_domain.get(domain)
        if signal is None:
            st.write(
                f"Não há indicador prioritário de {display_domain(domain)} "
                "disponível para os filtros selecionados."
            )
            continue
        st.write(
            f"{signal.display_name}: {signal.formatted_value} em {signal.period_label}."
        )
    st.markdown("**Comparações anuais**")
    financial_yoy = select_financial_yoy(frames.get("financial_facts"), filters=state)
    commerce_yoy = select_domain_yoy(frames, "Commerce", filters=state)
    fintech_yoy = select_domain_yoy(frames, "Fintech", filters=state)
    comparison_by_domain = {
        "Financial": ("Receita", financial_yoy),
        "Commerce": ("GMV", commerce_yoy),
        "Fintech": ("TPV", fintech_yoy),
    }
    for domain in story_domains:
        label, comparison = comparison_by_domain[domain]
        if comparison is None:
            st.write(
                f"Não há dados suficientes para estabelecer uma comparação "
                f"anual válida de {label} em {display_domain(domain)}."
            )
            continue
        period = format_period_label("QUARTER", comparison[0])
        st.write(
            f"{label} variou {format_metric(comparison[1], 'percent')} em "
            f"relação ao mesmo trimestre do ano anterior ({period}) — "
            f"{display_domain(domain)}."
        )
    st.markdown("**Limitações**")
    st.caption(
        "As séries resumidas têm definições e abrangências próprias. "
        "Movimentos paralelos entre Comércio e Serviços financeiros não "
        "demonstram usuários em comum nem causalidade. Comparações anuais "
        "usam a regra analítica existente e não estimam períodos ausentes."
    )

    interpretations = select_latest_interpretations(
        frames.get("interpretations"), filters=state
    )
    if interpretations:
        st.subheader("Interpretações registradas")
        for item in interpretations:
            st.markdown(f"**Interpretação · {item.metric_id}**")
            st.write(item.claim)
            st.caption(
                f"{item.source} · {format_date_br(item.reference_date)} · "
                f"ID da evidência: {item.evidence_id}"
            )

    st.subheader("Próxima exploração")
    st.write(
        "Consulte **Fontes e qualidade dos dados** para verificar "
        "disponibilidade, atualização e origem."
    )
    st.caption(
        "As datas de referência são exibidas por domínio. Comparações anuais "
        "reutilizam os cálculos analíticos existentes; não estimam observações "
        "ausentes nem acrescentam métricas."
    )
