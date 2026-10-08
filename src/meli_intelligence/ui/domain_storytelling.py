"""Pure, allowlisted presentation helpers for Commerce and Fintech pages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Mapping

import pandas as pd

from meli_intelligence.ui.filters import FilterState, apply_filters
from meli_intelligence.ui.presentation import format_compact_number, format_date, format_metric

MAX_DOMAIN_CARDS = 4
MAX_DOMAIN_INTERPRETATIONS = 3


@dataclass(frozen=True)
class DomainMetricSpec:
    dataset_id: str
    metric_id: str
    display_name: str
    context: str
    trend: bool = False


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
    DomainMetricSpec("operational_kpis", "gmv", "Gross merchandise volume (GMV)", "Reported Commerce volume.", True),
    DomainMetricSpec("operational_kpis", "unique_active_buyers", "Unique active buyers", "Reported unique buyers for the source period."),
    DomainMetricSpec("operational_kpis", "items_sold", "Items sold", "Reported item volume for the source period."),
)
FINTECH_METRICS = (
    DomainMetricSpec("operational_kpis", "fintech_mau", "Fintech monthly active users", "Reported monthly active-user measure."),
    DomainMetricSpec("operational_kpis", "tpv", "Total payment volume (TPV)", "Reported Fintech payment volume.", True),
    DomainMetricSpec("extended_operational_kpis", "aum", "Assets under management (AUM)", "Reported assets under management."),
    DomainMetricSpec("extended_operational_kpis", "credit_portfolio", "Credit portfolio", "Reported credit portfolio; source qualifier is preserved."),
    DomainMetricSpec("extended_operational_kpis", "npl_15_90_total", "15–90 day NPL", "MercadoLibre-reported 15–90 day non-performing loan ratio."),
)
DOMAIN_METRICS = {"Commerce": COMMERCE_METRICS, "Fintech": FINTECH_METRICS}
DOMAIN_QUESTIONS = {
    "Commerce": "What does reported evidence say about the scale, activity and trajectory of MercadoLibre Commerce?",
    "Fintech": "What does reported evidence say about the scale, activity and trajectory of Mercado Pago / MercadoLibre Fintech?",
}
DOMAIN_DATASETS = {
    "Commerce": ("operational_kpis",),
    "Fintech": ("operational_kpis", "extended_operational_kpis"),
}
DOMAIN_INTERPRETATION_METRICS = {
    "Commerce": frozenset({
        "gmv", "gmv_yoy_growth", "unique_active_buyers", "unique_active_buyers_yoy_growth",
        "items_sold", "items_sold_yoy_growth", "items_per_buyer",
    }),
    "Fintech": frozenset({
        "fintech_mau", "fintech_mau_yoy_growth", "tpv", "tpv_yoy_growth",
        "aum", "aum_yoy_growth", "credit_portfolio", "credit_portfolio_yoy_growth",
        "npl_15_90_total", "npl_15_90_yoy_change_pp",
    }),
}
DOMAIN_INTERPRETATION_LABELS = {
    "gmv_yoy_growth": "GMV year-over-year growth",
    "unique_active_buyers_yoy_growth": "Active buyers year-over-year growth",
    "items_sold_yoy_growth": "Items sold year-over-year growth",
    "items_per_buyer": "Items per buyer",
    "fintech_mau_yoy_growth": "Fintech active users year-over-year growth",
    "tpv_yoy_growth": "Payment volume year-over-year growth",
    "aum_yoy_growth": "Assets under management year-over-year growth",
    "credit_portfolio_yoy_growth": "Credit portfolio year-over-year growth",
    "npl_15_90_yoy_change_pp": "15–90 day NPL change",
}


def _date_column(frame: pd.DataFrame) -> str | None:
    return next((name for name in ("reference_date", "period_end", "date") if name in frame.columns), None)


def _filtered_rows(frame: pd.DataFrame | None, metric_id: str, filters: FilterState | None) -> pd.DataFrame:
    if frame is None or frame.empty or not {"metric_id", "value"}.issubset(frame.columns):
        return pd.DataFrame()
    state = (filters or FilterState()).validate()
    # Domain pages are semantically scoped by their explicit metric allowlist;
    # the shared global domain selection must not hide page facts.
    state = FilterState(start_date=state.start_date, end_date=state.end_date)
    selected = apply_filters(frame, state)
    selected = selected.loc[selected["metric_id"].astype(str) == metric_id].copy()
    date_column = _date_column(selected)
    if date_column is None:
        return pd.DataFrame()
    selected["_ui_reference_date"] = pd.to_datetime(selected[date_column], errors="coerce")
    return selected.loc[selected["_ui_reference_date"].notna()].copy()


def _friendly_value(value: float, unit: str) -> str:
    if unit in {"users", "items", "transactions", "count"}:
        compact = format_compact_number(value)
        label = {"users": "users", "items": "items", "transactions": "transactions", "count": ""}[unit]
        return f"{compact} {label}".strip()
    return format_metric(value, unit)


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
            raise ValueError(f"Metric selection contains an ID not allowlisted for {domain}.")
        specs = tuple(item for item in specs if item.metric_id in metric_ids)
    for spec in specs:
        rows = _filtered_rows(frames.get(spec.dataset_id), spec.metric_id, state)
        if rows.empty:
            continue
        for column in ("filing_date", "accession_number"):
            if column not in rows.columns:
                rows[column] = ""
        rows["_ui_filing_date"] = pd.to_datetime(rows["filing_date"], errors="coerce")
        rows = rows.sort_values(["_ui_reference_date", "_ui_filing_date", "accession_number"], kind="mergesort")
        row = rows.iloc[-1]
        try:
            value = float(row["value"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        unit = str(row.get("unit", "")) if pd.notna(row.get("unit")) else ""
        ref_date = pd.Timestamp(row["_ui_reference_date"]).date()
        period_label = str(row.get("period_label", "")).strip() if pd.notna(row.get("period_label")) else ""
        results.append(DomainMetric(
            metric_id=spec.metric_id,
            display_name=spec.display_name,
            business_domain=domain,
            value=value,
            formatted_value=_friendly_value(value, unit),
            unit=unit,
            reference_date=ref_date,
            period_label=period_label or format_date(ref_date),
            period_type=str(row.get("period_type", "")) if pd.notna(row.get("period_type")) else "",
            source=str(row.get("source", "Source not reported")) if pd.notna(row.get("source")) else "Source not reported",
            full_precision_value=f"{row['value']} {unit}".strip(),
            context=spec.context,
        ))
        if len(results) >= max_cards:
            break
    return tuple(results)


def domain_freshness(dataset_frames: Mapping[str, pd.DataFrame | None] | None, domain: str, *, filters: FilterState | None = None) -> date | None:
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
    spec = next((item for item in candidates if item.metric_id == metric_id), None) if metric_id else next((item for item in candidates if item.trend), None)
    if spec is None:
        if metric_id is not None:
            raise ValueError(f"Metric {metric_id!r} is not allowlisted for {domain}.")
        return pd.DataFrame(columns=["reference_date", "value", "period_label", "source"])
    rows = _filtered_rows((dataset_frames or {}).get(spec.dataset_id), spec.metric_id, filters)
    if rows.empty:
        return pd.DataFrame(columns=["reference_date", "value", "period_label", "source"])
    result = pd.DataFrame({
        "reference_date": rows["_ui_reference_date"].dt.date,
        "value": pd.to_numeric(rows["value"], errors="coerce"),
        "period_label": rows.get("period_label", rows["_ui_reference_date"].dt.strftime("%Y-%m-%d")),
        "source": rows.get("source", "Source not reported"),
    })
    result = result.loc[pd.to_numeric(result["value"], errors="coerce").map(math.isfinite)].copy()
    return result.sort_values("reference_date", kind="mergesort").reset_index(drop=True)


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
        selected = selected.loc[selected["business_domain"].astype(str) == domain].copy()
    else:
        metric_column = "source_metric_id" if "source_metric_id" in selected.columns else "metric_id"
        if metric_column not in selected.columns:
            return pd.DataFrame()
        selected = selected.loc[
            selected[metric_column].astype(str).isin(DOMAIN_INTERPRETATION_METRICS[domain])
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
    return selected.head(limit).drop(columns="_ui_reference_date").reset_index(drop=True)


def domain_data_status(health_records, domain: str) -> tuple[str, ...]:
    if domain not in DOMAIN_DATASETS:
        raise ValueError(f"Unsupported business domain: {domain}")
    health = {item.dataset_id: item for item in health_records}
    return tuple(
        f"{dataset_id}: {health[dataset_id].status}"
        for dataset_id in DOMAIN_DATASETS[domain]
        if dataset_id in health and health[dataset_id].status != "AVAILABLE"
    )


def domain_navigation_order() -> tuple[str, ...]:
    return (
        "Executive Overview", "Financial", "Commerce", "Fintech", "Macro", "PESTEL", "SWOT",
        "Product Evidence", "Market", "Data Quality & Sources",
    )


def domain_metric_label(metric_id: object, domain: str) -> str:
    """Map known source IDs to business labels without exposing backend IDs."""
    if domain not in DOMAIN_METRICS:
        raise ValueError(f"Unsupported business domain: {domain}")
    key = str(metric_id) if metric_id is not None else ""
    for spec in DOMAIN_METRICS[domain]:
        if spec.metric_id == key:
            return spec.display_name
    return DOMAIN_INTERPRETATION_LABELS.get(key, "Reported domain metric")


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


def render_domain_page(st, health_records, domain: str, filters: FilterState | None = None) -> None:
    """Render the shared, read-only narrative shell for a domain page."""
    from meli_intelligence.ui.data import load_dataset

    state = (filters or FilterState()).validate()
    date_filters = FilterState(start_date=state.start_date, end_date=state.end_date).validate()
    health_by_id = {item.dataset_id: item for item in health_records}
    frames: dict[str, pd.DataFrame | None] = {}
    read_errors: list[str] = []
    for dataset_id in DOMAIN_DATASETS[domain]:
        item = health_by_id.get(dataset_id)
        if item is None or item.status != "AVAILABLE":
            frames[dataset_id] = None
            continue
        try:
            frames[dataset_id] = load_dataset(dataset_id, path=item.path, filters=date_filters)
        except Exception as exc:
            frames[dataset_id] = None
            read_errors.append(f"{dataset_id}: {type(exc).__name__}")

    latest = domain_freshness(frames, domain, filters=date_filters)
    st.title(domain)
    st.caption(DOMAIN_QUESTIONS[domain])
    st.caption(f"Latest reference date: {format_date(latest)}")
    st.caption("Commerce and Fintech figures are separate aggregate series; parallel movement does not establish user overlap or causality.")

    degraded = domain_data_status(health_records, domain)
    if degraded:
        st.warning("Data availability is limited: " + "; ".join(degraded) + ". See Data Quality & Sources for details.")
    if read_errors:
        st.warning("Available datasets could not be loaded for this view: " + "; ".join(read_errors) + ".")

    signals = select_domain_snapshots(frames, domain, filters=date_filters)
    if signals:
        columns = st.columns(min(len(signals), MAX_DOMAIN_CARDS))
        for column, signal in zip(columns, signals):
            with column:
                st.metric(signal.display_name, signal.formatted_value)
                period = signal.period_label
                if signal.period_type:
                    period = f"{period} · {signal.period_type.lower()}"
                st.caption(f"{period} · Reference date: {format_date(signal.reference_date)}")
                st.caption(signal.context)
                with st.expander("Source and reported precision"):
                    st.write(f"Source: {signal.source}")
                    st.write(f"Value as loaded: {signal.full_precision_value}")
    else:
        st.info("No priority metric is available for the selected period. Missing values are not replaced with zero.")

    missing = domain_metric_availability(frames, domain, filters=date_filters)
    if missing:
        st.caption("Priority metrics unavailable in the selected data: " + ", ".join(missing) + ".")

    trend_spec = next(spec for spec in DOMAIN_METRICS[domain] if spec.trend)
    trend = select_domain_trend(frames, domain, metric_id=trend_spec.metric_id, filters=date_filters)
    st.subheader(f"Reported {trend_spec.display_name}")
    if trend.empty:
        st.info(f"No reported time series is available for {trend_spec.display_name} in this period.")
    else:
        st.caption(f"{trend_spec.display_name} · reported source observations; no values are interpolated or resampled.")
        st.line_chart(trend, x="reference_date", y="value", x_label="Reference date", y_label=trend_spec.display_name)

    interpretations = None
    item = health_by_id.get("interpretations")
    if item is not None and item.status == "AVAILABLE":
        try:
            interpretation_frame = load_dataset("interpretations", path=item.path, filters=date_filters)
            interpretations = select_domain_interpretations(interpretation_frame, domain, filters=date_filters)
        except Exception as exc:
            st.warning(f"Existing interpretations could not be loaded: {type(exc).__name__}.")
    st.subheader("Existing interpretations")
    if interpretations is None or interpretations.empty:
        st.info("No existing interpretation is available for this domain and period.")
    else:
        for _, row in interpretations.iterrows():
            metric_id = row.get("source_metric_id", row.get("metric_id"))
            st.markdown(f"**Interpretation · {domain_metric_label(metric_id, domain)}**")
            st.write(str(row.get("claim", "")))
            date_value = next((row.get(column) for column in ("reference_date", "period_end", "date") if column in row.index), None)
            st.caption(f"{row.get('source', 'Source not reported')} · {format_date(date_value)} · Evidence ID: {row.get('evidence_id', 'Unavailable')}")

    with st.expander("Methodology and domain limits"):
        st.write("Commerce and Fintech indicators are reported as separate aggregate series. Concurrent movement does not establish shared users, user overlap, cross-domain retention or frequency, cross-sell, an ecosystem-user count, or causality.")
        st.write("Only existing source observations and existing interpretations are shown. This page does not calculate growth rates or make Product recommendations.")
    if domain == "Fintech":
        with st.expander("Additional reported credit quality context"):
            npl = select_domain_snapshots(frames, domain, filters=date_filters, max_cards=1, metric_ids=("npl_15_90_total",))
            if npl:
                item = npl[0]
                st.write(f"{item.display_name}: {item.formatted_value}")
                st.caption(f"{item.period_label} · Reference date: {format_date(item.reference_date)} · {item.source}")
                st.caption("This is MercadoLibre's reported 15–90 day measure; it is not the BCB household delinquency series above 90 days.")
            else:
                st.info("No reported 15–90 day NPL observation is available for the selected period.")
    st.caption("Use the date filters to narrow the reported periods. Data freshness is based on reference dates, not filing dates.")
