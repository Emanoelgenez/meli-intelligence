"""Pure, allowlisted presentation helpers for Commerce and Fintech pages."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping

import pandas as pd

from meli_intelligence.analytics.operational import (
    calculate_yoy_growth as calculate_operational_yoy_growth,
)
from meli_intelligence.ui.filters import FilterState, apply_filters
from meli_intelligence.ui.presentation import (
    format_count,
    format_date_br,
    format_metric,
    format_period_label,
    format_status,
)
from meli_intelligence.ui.temporal_charts import (
    chart_frame,
    chart_history,
    quarterly_chart_spec,
    render_series_coverage,
)

MAX_DOMAIN_CARDS = 4
MAX_DOMAIN_INTERPRETATIONS = 3


@dataclass(frozen=True)
class DomainMetricSpec:
    dataset_id: str
    metric_id: str
    display_name: str
    context: str
    trend: bool = False
    period_type: str = "QUARTER"


@dataclass(frozen=True)
class DomainMetric:
    metric_id: str
    display_name: str
    business_domain: str
    value: float
    formatted_value: str
    unit: str
    reference_date: date
    period_label: str
    period_type: str
    source: str
    full_precision_value: str
    context: str


COMMERCE_METRICS = (
    DomainMetricSpec(
        "operational_kpis",
        "gmv",
        "Volume bruto de mercadorias (GMV)",
        "Volume de comércio reportado.",
        True,
    ),
    DomainMetricSpec(
        "operational_kpis",
        "unique_active_buyers",
        "Compradores ativos únicos",
        "Compradores únicos reportados no período.",
    ),
    DomainMetricSpec(
        "operational_kpis",
        "items_sold",
        "Itens vendidos",
        "Quantidade de itens reportada no período.",
    ),
)
FINTECH_METRICS = (
    DomainMetricSpec(
        "operational_kpis",
        "fintech_mau",
        "Usuários ativos mensais (Fintech)",
        "Indicador reportado de usuários ativos mensais.",
        period_type="INSTANT",
    ),
    DomainMetricSpec(
        "operational_kpis",
        "tpv",
        "Volume total de pagamentos (TPV)",
        "Volume de pagamentos reportado.",
        True,
    ),
    DomainMetricSpec(
        "extended_operational_kpis",
        "aum",
        "Ativos sob gestão (AUM)",
        "Ativos sob gestão reportados.",
        period_type="INSTANT",
    ),
    DomainMetricSpec(
        "extended_operational_kpis",
        "credit_portfolio",
        "Carteira de crédito",
        "Carteira de crédito reportada; o qualificador da fonte é preservado.",
        period_type="INSTANT",
    ),
    DomainMetricSpec(
        "extended_operational_kpis",
        "npl_15_90_total",
        "Inadimplência de 15 a 90 dias",
        "Índice de inadimplência de 15 a 90 dias reportado pelo Mercado Livre.",
        period_type="INSTANT",
    ),
)
DOMAIN_METRICS = {"Commerce": COMMERCE_METRICS, "Fintech": FINTECH_METRICS}
DOMAIN_QUESTIONS = {
    "Commerce": (
        "O que os dados reportados mostram sobre a escala, a atividade "
        "e a evolução do comércio do Mercado Livre?"
    ),
    "Fintech": (
        "O que os dados reportados mostram sobre a escala, a atividade "
        "e a evolução dos serviços financeiros do Mercado Livre?"
    ),
}
DOMAIN_DATASETS = {
    "Commerce": ("operational_kpis",),
    "Fintech": ("operational_kpis", "extended_operational_kpis"),
}
DOMAIN_INTERPRETATION_METRICS = {
    "Commerce": frozenset(
        {
            "gmv",
            "gmv_yoy_growth",
            "unique_active_buyers",
            "unique_active_buyers_yoy_growth",
            "items_sold",
            "items_sold_yoy_growth",
            "items_per_buyer",
        }
    ),
    "Fintech": frozenset(
        {
            "fintech_mau",
            "fintech_mau_yoy_growth",
            "tpv",
            "tpv_yoy_growth",
            "aum",
            "aum_yoy_growth",
            "credit_portfolio",
            "credit_portfolio_yoy_growth",
            "npl_15_90_total",
            "npl_15_90_yoy_change_pp",
        }
    ),
}
DOMAIN_INTERPRETATION_LABELS = {
    "gmv_yoy_growth": "Crescimento anual do GMV",
    "unique_active_buyers_yoy_growth": "Crescimento anual de compradores ativos",
    "items_sold_yoy_growth": "Crescimento anual de itens vendidos",
    "items_per_buyer": "Itens por comprador",
    "fintech_mau_yoy_growth": "Crescimento anual de usuários ativos do Fintech",
    "tpv_yoy_growth": "Crescimento anual do TPV",
    "aum_yoy_growth": "Crescimento anual de ativos sob gestão",
    "credit_portfolio_yoy_growth": "Crescimento anual da carteira de crédito",
    "npl_15_90_yoy_change_pp": "Variação anual da inadimplência de 15 a 90 dias",
}


def _date_column(frame: pd.DataFrame) -> str | None:
    return next(
        (
            name
            for name in ("reference_date", "period_end", "date")
            if name in frame.columns
        ),
        None,
    )


def _filtered_rows(
    frame: pd.DataFrame | None, metric_id: str, filters: FilterState | None
) -> pd.DataFrame:
    if (
        frame is None
        or frame.empty
        or not {"metric_id", "value"}.issubset(frame.columns)
    ):
        return pd.DataFrame()
    state = (filters or FilterState()).validate()
    # Domain pages are semantically scoped by their explicit metric allowlist;
    # the shared global domain selection must not hide page facts.
    state = FilterState(start_date=state.start_date, end_date=state.end_date)
    selected = apply_filters(frame, state)
    selected = selected.loc[selected["metric_id"].astype(str) == metric_id].copy()
    spec = next(
        item
        for specs in DOMAIN_METRICS.values()
        for item in specs
        if item.metric_id == metric_id
    )
    if "period_type" not in selected:
        return pd.DataFrame()
    selected = selected.loc[
        selected.period_type.astype(str).str.upper().eq(spec.period_type)
    ].copy()
    date_column = "period_end" if "period_end" in selected else _date_column(selected)
    if date_column is None:
        return pd.DataFrame()
    selected["_ui_reference_date"] = pd.to_datetime(
        selected[date_column], errors="coerce"
    )
    return selected.loc[selected["_ui_reference_date"].notna()].copy()


def _friendly_value(value: float, unit: str) -> str:
    if unit in {"items", "transactions", "count"}:
        noun = {"items": "itens", "transactions": "transações", "count": ""}[unit]
    elif unit == "users":
        noun = "usuários"
    else:
        return format_metric(value, unit)
    return format_count(value, noun)


def select_domain_snapshots(
    dataset_frames: Mapping[str, pd.DataFrame | None] | None,
    domain: str,
    *,
    filters: FilterState | None = None,
    max_cards: int = MAX_DOMAIN_CARDS,
    metric_ids: tuple[str, ...] | None = None,
) -> tuple[DomainMetric, ...]:
    """Select latest source facts in fixed domain priority order; never calculate."""
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    if not isinstance(max_cards, int) or not 0 <= max_cards <= MAX_DOMAIN_CARDS:
        raise ValueError(f"max_cards must be between 0 and {MAX_DOMAIN_CARDS}.")
    if max_cards == 0:
        return ()
    state = (filters or FilterState()).validate()
    frames = dataset_frames or {}
    results: list[DomainMetric] = []
    specs = DOMAIN_METRICS[domain]
    if metric_ids is not None:
        allowed = {item.metric_id for item in specs}
        if any(metric_id not in allowed for metric_id in metric_ids):
            raise ValueError(
                f"Metric selection contains an ID not allowlisted for {domain}."
            )
        specs = tuple(item for item in specs if item.metric_id in metric_ids)
    for spec in specs:
        rows = _filtered_rows(frames.get(spec.dataset_id), spec.metric_id, state)
        if rows.empty:
            continue
        for column in ("filing_date", "accession_number"):
            if column not in rows.columns:
                rows[column] = ""
        rows["_ui_filing_date"] = pd.to_datetime(rows["filing_date"], errors="coerce")
        rows = rows.sort_values(
            ["_ui_reference_date", "_ui_filing_date", "accession_number"],
            kind="mergesort",
        )
        row = rows.iloc[-1]
        try:
            value = float(row["value"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        unit = str(row.get("unit", "")) if pd.notna(row.get("unit")) else ""
        ref_date = pd.Timestamp(row["_ui_reference_date"]).date()
        period_label = (
            str(row.get("period_label", "")).strip()
            if pd.notna(row.get("period_label"))
            else ""
        )
        period_label = format_period_label(spec.period_type, ref_date, period_label)
        results.append(
            DomainMetric(
                metric_id=spec.metric_id,
                display_name=spec.display_name,
                business_domain=domain,
                value=value,
                formatted_value=_friendly_value(value, unit),
                unit=unit,
                reference_date=ref_date,
                period_label=period_label or format_date_br(ref_date),
                period_type=str(row.get("period_type", ""))
                if pd.notna(row.get("period_type"))
                else "",
                source=str(row.get("source", "Fonte não informada"))
                if pd.notna(row.get("source"))
                else "Fonte não informada",
                full_precision_value=f"{row['value']} {unit}".strip(),
                context=spec.context,
            )
        )
        if len(results) >= max_cards:
            break
    return tuple(results)


def domain_freshness(
    dataset_frames: Mapping[str, pd.DataFrame | None] | None,
    domain: str,
    *,
    filters: FilterState | None = None,
) -> date | None:
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    frames = dataset_frames or {}
    state = (filters or FilterState()).validate()
    dates = []
    for spec in DOMAIN_METRICS[domain]:
        rows = _filtered_rows(frames.get(spec.dataset_id), spec.metric_id, state)
        if not rows.empty:
            dates.extend(rows["_ui_reference_date"].dt.date.tolist())
    return max(dates) if dates else None


def select_domain_trend(
    dataset_frames: Mapping[str, pd.DataFrame | None] | None,
    domain: str,
    *,
    metric_id: str | None = None,
    filters: FilterState | None = None,
) -> pd.DataFrame:
    """Return reported points in chronological order, without resampling or filling."""
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    candidates = DOMAIN_METRICS[domain]
    spec = (
        next((item for item in candidates if item.metric_id == metric_id), None)
        if metric_id
        else next((item for item in candidates if item.trend), None)
    )
    if spec is None:
        if metric_id is not None:
            raise ValueError(f"Metric {metric_id!r} is not allowlisted for {domain}.")
        return pd.DataFrame(
            columns=["reference_date", "value", "period_label", "unit", "source"]
        )
    rows = _filtered_rows(
        (dataset_frames or {}).get(spec.dataset_id), spec.metric_id, filters
    )
    if rows.empty:
        return pd.DataFrame(
            columns=["reference_date", "value", "period_label", "unit", "source"]
        )
    result = pd.DataFrame(
        {
            "reference_date": rows["_ui_reference_date"].dt.date,
            "value": pd.to_numeric(rows["value"], errors="coerce"),
            "period_label": [
                format_period_label(spec.period_type, value, label)
                for value, label in zip(
                    rows["_ui_reference_date"],
                    rows.get("period_label", pd.Series("", index=rows.index)),
                    strict=True,
                )
            ],
            "unit": rows.get("unit", ""),
            "source": rows.get("source", "Fonte não informada"),
        }
    )
    result = result.loc[
        pd.to_numeric(result["value"], errors="coerce").map(math.isfinite)
    ].copy()
    return result.sort_values("reference_date", kind="mergesort").reset_index(drop=True)


def select_domain_yoy(
    dataset_frames: Mapping[str, pd.DataFrame | None] | None,
    domain: str,
    *,
    filters: FilterState | None = None,
) -> tuple[date, float] | None:
    """Reuse operational analytics for the latest selected quarterly trend point."""
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    spec = next(item for item in DOMAIN_METRICS[domain] if item.trend)
    current = select_domain_trend(
        dataset_frames, domain, metric_id=spec.metric_id, filters=filters
    )
    if current.empty:
        return None
    current_date = pd.Timestamp(current.iloc[-1]["reference_date"]).date()
    facts = (dataset_frames or {}).get(spec.dataset_id)
    if facts is None or facts.empty:
        return None
    try:
        comparisons = calculate_operational_yoy_growth(facts, spec.metric_id)
    except (KeyError, TypeError, ValueError):
        return None
    if comparisons.empty:
        return None
    comparisons = comparisons.loc[
        comparisons["period_type"].astype(str).str.upper().eq("QUARTER")
    ].copy()
    if comparisons.empty:
        return None
    comparisons["_period_end"] = pd.to_datetime(
        comparisons["period_end"], errors="coerce"
    )
    selected = comparisons.loc[comparisons["_period_end"].dt.date.eq(current_date)]
    if selected.empty:
        return None
    try:
        value = float(selected.iloc[-1]["value"])
    except (TypeError, ValueError, OverflowError):
        return None
    return (current_date, value) if math.isfinite(value) else None


def select_domain_interpretations(
    frame: pd.DataFrame | None,
    domain: str,
    *,
    filters: FilterState | None = None,
    limit: int = MAX_DOMAIN_INTERPRETATIONS,
) -> pd.DataFrame:
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    if not isinstance(limit, int) or not 0 <= limit <= MAX_DOMAIN_INTERPRETATIONS:
        raise ValueError(f"limit must be between 0 and {MAX_DOMAIN_INTERPRETATIONS}.")
    if frame is None or frame.empty or "evidence_type" not in frame.columns:
        return pd.DataFrame()
    selected = frame.loc[frame["evidence_type"].astype(str) == "INTERPRETATION"].copy()
    if "business_domain" in selected.columns:
        selected = selected.loc[
            selected["business_domain"].astype(str) == domain
        ].copy()
    else:
        metric_column = (
            "source_metric_id"
            if "source_metric_id" in selected.columns
            else "metric_id"
        )
        if metric_column not in selected.columns:
            return pd.DataFrame()
        selected = selected.loc[
            selected[metric_column]
            .astype(str)
            .isin(DOMAIN_INTERPRETATION_METRICS[domain])
        ].copy()
    state = (filters or FilterState()).validate()
    selected = apply_filters(
        selected,
        FilterState(start_date=state.start_date, end_date=state.end_date),
    )
    column = _date_column(selected)
    if column is None:
        return pd.DataFrame()
    selected["_ui_reference_date"] = pd.to_datetime(selected[column], errors="coerce")
    selected = selected.loc[selected["_ui_reference_date"].notna()].sort_values(
        ["_ui_reference_date", "evidence_id"], ascending=[False, True], kind="mergesort"
    )
    return (
        selected.head(limit).drop(columns="_ui_reference_date").reset_index(drop=True)
    )


def domain_data_status(health_records, domain: str) -> tuple[str, ...]:
    if domain not in DOMAIN_DATASETS:
        raise ValueError(f"Unsupported business domain: {domain}")
    health = {item.dataset_id: item for item in health_records}
    domain_label = "Comércio" if domain == "Commerce" else "serviços financeiros"
    messages = []
    for dataset_id in DOMAIN_DATASETS[domain]:
        item = health.get(dataset_id)
        if item is None or item.status == "AVAILABLE":
            continue
        label = (
            "Indicadores complementares de serviços financeiros"
            if dataset_id == "extended_operational_kpis"
            else f"Indicadores de {domain_label}"
        )
        messages.append(f"{label}: {format_status(item.status)}")
    return tuple(messages)


def domain_navigation_order() -> tuple[str, ...]:
    """Return the legacy page inventory for callers that still inspect it."""
    return (
        "Executive Overview",
        "Financial",
        "Commerce",
        "Fintech",
        "Macro",
        "PESTEL",
        "SWOT",
        "Product Evidence",
        "Market",
        "Data Quality & Sources",
    )


def domain_metric_label(metric_id: object, domain: str) -> str:
    """Map known source IDs to business labels without exposing backend IDs."""
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    key = str(metric_id) if metric_id is not None else ""
    for spec in DOMAIN_METRICS[domain]:
        if spec.metric_id == key:
            return spec.display_name
    return DOMAIN_INTERPRETATION_LABELS.get(key, "Indicador de negócio reportado")


def domain_metric_availability(
    dataset_frames: Mapping[str, pd.DataFrame | None] | None,
    domain: str,
    *,
    filters: FilterState | None = None,
) -> tuple[str, ...]:
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    frames = dataset_frames or {}
    state = (filters or FilterState()).validate()
    return tuple(
        spec.display_name
        for spec in DOMAIN_METRICS[domain]
        if _filtered_rows(frames.get(spec.dataset_id), spec.metric_id, state).empty
    )


def render_domain_page(
    st, health_records, domain: str, filters: FilterState | None = None
) -> None:
    """Render the shared, read-only narrative shell for a domain page."""
    from meli_intelligence.ui.data import load_dataset

    state = (filters or FilterState()).validate()
    date_filters = FilterState(
        start_date=state.start_date, end_date=state.end_date
    ).validate()
    health_by_id = {item.dataset_id: item for item in health_records}
    frames: dict[str, pd.DataFrame | None] = {}
    read_errors: list[str] = []
    for dataset_id in DOMAIN_DATASETS[domain]:
        item = health_by_id.get(dataset_id)
        if item is None or item.status != "AVAILABLE":
            frames[dataset_id] = None
            if item is None:
                read_errors.append(
                    f"{dataset_id}: indisponível — conjunto não cadastrado"
                )
            continue
        try:
            frames[dataset_id] = load_dataset(dataset_id, path=item.path)
        except Exception as exc:
            frames[dataset_id] = None
            read_errors.append(f"{dataset_id}: {type(exc).__name__}")

    latest = domain_freshness(frames, domain, filters=date_filters)
    page_titles = {"Commerce": "Comércio", "Fintech": "Serviços financeiros"}
    st.title(page_titles[domain])
    st.caption(DOMAIN_QUESTIONS[domain])
    st.caption(f"Data de referência mais recente: {format_date_br(latest)}")
    degraded = domain_data_status(health_records, domain)
    if degraded:
        st.warning(
            "Disponibilidade de dados limitada: "
            + "; ".join(degraded)
            + ". Consulte Fontes e qualidade dos dados."
        )
    if read_errors:
        st.warning(
            "Não foi possível carregar os conjuntos disponíveis para esta página: "
            + "; ".join(read_errors)
            + "."
        )

    signals = select_domain_snapshots(frames, domain, filters=date_filters)
    if signals:
        columns = st.columns(min(len(signals), MAX_DOMAIN_CARDS))
        for column, signal in zip(columns, signals):
            with column:
                st.metric(signal.display_name, signal.formatted_value)
                period = signal.period_label
                if signal.period_type:
                    qualifier = (
                        "posição instantânea"
                        if signal.period_type == "INSTANT"
                        else "trimestre"
                    )
                    period = f"{period} · {qualifier}"
                st.caption(
                    f"{period} · Data de referência: "
                    f"{format_date_br(signal.reference_date)}"
                )
                st.caption(signal.context)
                with st.expander("Fonte e precisão reportada"):
                    st.write(f"Fonte: {signal.source}")
                    st.write(f"Valor conforme carregado: {signal.full_precision_value}")
    else:
        st.info(
            "Nenhum indicador prioritário está disponível neste período. "
            "Valores ausentes não são substituídos por zero."
        )

    missing = domain_metric_availability(frames, domain, filters=date_filters)
    if missing:
        st.caption(
            "Indicadores prioritários indisponíveis nos dados selecionados: "
            + ", ".join(missing)
            + "."
        )

    trend_spec = next(spec for spec in DOMAIN_METRICS[domain] if spec.trend)
    trend = select_domain_trend(
        frames, domain, metric_id=trend_spec.metric_id, filters=date_filters
    )
    st.subheader(trend_spec.display_name)
    if trend.empty:
        st.info(f"Não há série reportada de {trend_spec.display_name} neste período.")
    else:
        st.caption(
            f"{trend_spec.display_name} · observações da fonte; sem interpolação."
        )
        full_series = select_domain_trend(
            frames, domain, metric_id=trend_spec.metric_id
        )
        render_series_coverage(st, trend, "reference_date", full_series=full_series)
        full_history = st.checkbox("Exibir todo o histórico", key=f"historico_{domain}")
        visible_trend = chart_history(trend, full_history=full_history)
        unit = str(trend.get("unit", pd.Series([""])).iloc[0])
        chart = chart_frame(
            visible_trend,
            "reference_date",
            trend_spec.display_name,
            unit=unit,
            definition=trend_spec.context,
        )
        st.vega_lite_chart(
            chart,
            quarterly_chart_spec(
                chart,
                "reference_date",
                trend_spec.display_name,
                unit=unit,
                definition=trend_spec.context,
            ),
            width="stretch",
        )

    st.subheader("O que os dados mostram")
    st.markdown("**Fato observado**")
    if trend.empty:
        st.write(
            f"Não há observação trimestral de {trend_spec.display_name} "
            "para os filtros selecionados."
        )
    else:
        latest = trend.iloc[-1]
        latest_period = format_period_label(
            "QUARTER", latest["reference_date"], latest["period_label"]
        )
        st.write(
            f"{trend_spec.display_name} atingiu "
            f"{format_metric(latest['value'], str(latest['unit']))} "
            f"em {latest_period}."
        )

    st.markdown("**Comparação anual**")
    comparison = select_domain_yoy(frames, domain, filters=date_filters)
    if comparison is None:
        period = latest_period if not trend.empty else "o período selecionado"
        st.write(
            f"Não há dados suficientes para estabelecer uma comparação anual "
            f"válida de {trend_spec.display_name} em {period}."
        )
    else:
        period = format_period_label("QUARTER", comparison[0])
        st.write(
            f"{trend_spec.display_name} variou "
            f"{format_metric(comparison[1], 'percent')} em relação ao mesmo "
            f"trimestre do ano anterior ({period})."
        )
    st.markdown("**Limitações**")
    limitation = (
        "Os indicadores de Comércio e Serviços financeiros são séries agregadas "
        "distintas. Movimentos paralelos não demonstram usuários em comum nem "
        "causalidade. "
        if domain in {"Commerce", "Fintech"}
        else ""
    )
    st.caption(
        limitation
        + "A comparação usa observações trimestrais equivalentes e respeita a "
        "unidade e a definição reportadas. Períodos ausentes não são estimados."
    )

    interpretations = None
    item = health_by_id.get("interpretations")
    if item is not None and item.status == "AVAILABLE":
        try:
            interpretation_frame = load_dataset(
                "interpretations", path=item.path, filters=date_filters
            )
            interpretations = select_domain_interpretations(
                interpretation_frame, domain, filters=date_filters
            )
        except Exception as exc:
            st.warning(
                "Não foi possível carregar as interpretações existentes: "
                f"{type(exc).__name__}."
            )
    if interpretations is not None and not interpretations.empty:
        st.subheader("Interpretações registradas")
        for _, row in interpretations.iterrows():
            metric_id = row.get("source_metric_id", row.get("metric_id"))
            st.markdown(f"**Interpretação · {domain_metric_label(metric_id, domain)}**")
            st.write(str(row.get("claim", "")))
            date_value = next(
                (
                    row.get(column)
                    for column in ("reference_date", "period_end", "date")
                    if column in row.index
                ),
                None,
            )
            st.caption(
                f"{row.get('source', 'Fonte não informada')} · "
                f"{format_date_br(date_value)} · ID da evidência: "
                f"{row.get('evidence_id', 'Indisponível')}"
            )

    with st.expander("Metodologia e limites"):
        st.write(
            "Os indicadores de Comércio e Serviços financeiros são séries "
            "agregadas distintas. Movimentos simultâneos não demonstram "
            "usuários compartilhados, retenção entre áreas, venda cruzada, "
            "contagem de usuários do ecossistema ou causalidade."
        )
        st.write(
            "A variação anual usa a função analítica existente e só é exibida "
            "quando há períodos trimestrais comparáveis. A página preserva as "
            "observações reportadas, não preenche lacunas nem apresenta "
            "recomendações de produto."
        )
    if domain == "Fintech":
        with st.expander("Contexto adicional de qualidade do crédito"):
            npl = select_domain_snapshots(
                frames,
                domain,
                filters=date_filters,
                max_cards=1,
                metric_ids=("npl_15_90_total",),
            )
            if npl:
                item = npl[0]
                st.write(f"{item.display_name}: {item.formatted_value}")
                st.caption(
                    f"{item.period_label} · Data de referência: "
                    f"{format_date_br(item.reference_date)} · {item.source}"
                )
                st.caption(
                    "Esta é a medida reportada pelo Mercado Livre para 15 a 90 "
                    "dias; ela difere da série do Banco Central acima de 90 dias."
                )
            else:
                st.info(
                    "Não há observação reportada de inadimplência de 15 a 90 "
                    "dias para o período selecionado."
                )
    st.caption(
        "Use os filtros de data para delimitar os períodos. A atualização "
        "dos dados considera a data de referência, não a data de protocolo."
    )
