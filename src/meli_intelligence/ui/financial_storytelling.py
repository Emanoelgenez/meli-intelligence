"""Pure, allowlisted presentation helpers for reported Financial facts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import pandas as pd

from meli_intelligence.ui.filters import FilterState, apply_filters
from meli_intelligence.ui.presentation import format_date, format_metric, select_latest_interpretations

MAX_FINANCIAL_CARDS = 4
MAX_FINANCIAL_INTERPRETATIONS = 3


@dataclass(frozen=True)
class FinancialMetricSpec:
    metric_id: str
    display_name: str
    period_type: str
    context: str
    primary_trend: bool = False


@dataclass(frozen=True)
class FinancialFact:
    metric_id: str
    display_name: str
    value: float
    formatted_value: str
    unit: str
    period_start: date | None
    period_end: date
    period_type: str
    period_label: str
    filing_date: date | None
    form: str
    accession_number: str
    source: str
    full_precision_value: str
    context: str


# These IDs are the actual concepts normalized by SEC Company Facts. The
# overview is intentionally limited to quarterly duration facts.
FINANCIAL_PRIORITY = (
    FinancialMetricSpec("net_revenues_financial_income", "Revenue and financial income", "QUARTER", "Reported quarterly revenue facts.", True),
    FinancialMetricSpec("operating_income", "Operating income", "QUARTER", "Reported quarterly operating income."),
    FinancialMetricSpec("net_income", "Net income", "QUARTER", "Reported quarterly net income."),
    FinancialMetricSpec("operating_cash_flow", "Operating cash flow", "QUARTER", "Reported quarterly operating cash flow."),
)
FINANCIAL_CONTEXT = (
    FinancialMetricSpec("gross_profit", "Gross profit", "QUARTER", "Reported quarterly gross profit."),
    FinancialMetricSpec("capex_productive_assets", "Capital expenditures on productive assets", "QUARTER", "Reported productive-asset cash expenditures."),
    FinancialMetricSpec("cash_and_equivalents", "Cash and cash equivalents", "INSTANT", "Reported balance-sheet amount at period end."),
    FinancialMetricSpec("total_assets", "Total assets", "INSTANT", "Reported balance-sheet amount at period end."),
    FinancialMetricSpec("total_liabilities", "Total liabilities", "INSTANT", "Reported balance-sheet amount at period end."),
    FinancialMetricSpec("stockholders_equity", "Stockholders' equity", "INSTANT", "Reported balance-sheet amount at period end."),
)
FINANCIAL_SPECS = FINANCIAL_PRIORITY + FINANCIAL_CONTEXT
FINANCIAL_LABELS = {spec.metric_id: spec.display_name for spec in FINANCIAL_SPECS}
FINANCIAL_QUESTION = "What do MercadoLibre's reported financials say about growth, profitability, cash generation and balance-sheet position?"
_REQUIRED_COLUMNS = frozenset({"metric_id", "value", "unit", "period_end", "period_type"})


def _date_filters(filters: FilterState | None) -> FilterState:
    state = (filters or FilterState()).validate()
    # This page is semantically Financial even when a global domain filter is set.
    return FilterState(start_date=state.start_date, end_date=state.end_date).validate()


def _rows(frame: pd.DataFrame | None, spec: FinancialMetricSpec, filters: FilterState | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    missing = _REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"financial_facts is missing required columns: {sorted(missing)}")
    result = apply_filters(frame, _date_filters(filters))
    result = result.loc[
        result.metric_id.astype(str).eq(spec.metric_id)
        & result.period_type.astype(str).str.upper().eq(spec.period_type)
    ].copy()
    result["_period_end"] = pd.to_datetime(result.period_end, errors="coerce")
    result = result.loc[result._period_end.notna()].copy()
    if "period_start" not in result:
        result["period_start"] = pd.NaT
    result["_period_start"] = pd.to_datetime(result.period_start, errors="coerce")
    key = ["metric_id", "unit", "period_type", "_period_start", "_period_end"]
    if result.duplicated(key, keep=False).any():
        raise ValueError(f"Duplicate financial economic keys for metric {spec.metric_id!r}.")
    result["_value"] = pd.to_numeric(result.value, errors="coerce")
    result = result.loc[result._value.map(lambda item: math.isfinite(float(item)) if pd.notna(item) else False)].copy()
    return result.sort_values(["_period_end", "_period_start"], kind="mergesort").reset_index(drop=True)


def _as_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _to_fact(row: pd.Series, spec: FinancialMetricSpec) -> FinancialFact:
    value = float(row["_value"])
    unit = str(row.get("unit", "")) if pd.notna(row.get("unit")) else ""
    end = _as_date(row.get("_period_end"))
    if end is None:
        raise ValueError("A selected financial fact must have period_end.")
    start = _as_date(row.get("_period_start"))
    return FinancialFact(
        metric_id=spec.metric_id,
        display_name=spec.display_name,
        value=value,
        formatted_value=format_metric(value, unit),
        unit=unit,
        period_start=start,
        period_end=end,
        period_type=spec.period_type,
        period_label=str(row.get("period_label", "") or "").strip() or format_date(end),
        filing_date=_as_date(row.get("filed_at")),
        form=str(row.get("form", "") or ""),
        accession_number=str(row.get("accession_number", "") or ""),
        source=str(row.get("source", "Source not reported") or "Source not reported"),
        full_precision_value=f"{row.get('value')} {unit}".strip(),
        context=spec.context,
    )


def select_financial_snapshots(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    max_cards: int = MAX_FINANCIAL_CARDS,
) -> tuple[FinancialFact, ...]:
    """Select latest allowlisted quarterly facts; perform no financial calculations."""
    if not isinstance(max_cards, int) or not 0 <= max_cards <= MAX_FINANCIAL_CARDS:
        raise ValueError(f"max_cards must be between 0 and {MAX_FINANCIAL_CARDS}.")
    selected: list[FinancialFact] = []
    for spec in FINANCIAL_PRIORITY:
        rows = _rows(frame, spec, filters)
        if not rows.empty:
            selected.append(_to_fact(rows.iloc[-1], spec))
        if len(selected) >= max_cards:
            break
    return tuple(selected)


def select_financial_trend(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    metric_id: str = "net_revenues_financial_income",
) -> pd.DataFrame:
    """Return reported quarterly revenue points in time order without filling gaps."""
    spec = next((item for item in FINANCIAL_PRIORITY if item.metric_id == metric_id and item.primary_trend), None)
    if spec is None:
        raise ValueError(f"Metric {metric_id!r} is not allowlisted for the Financial trend.")
    rows = _rows(frame, spec, filters)
    if rows.empty:
        return pd.DataFrame(columns=["period_start", "period_end", "value", "unit", "period_label", "source"])
    columns = ["period_start", "period_end", "_value", "unit"]
    for optional in ("period_label", "source"):
        if optional in rows.columns:
            columns.append(optional)
    result = rows[columns].rename(columns={"_value": "value"}).copy()
    result["period_start"] = pd.to_datetime(result["period_start"], errors="coerce")
    result["period_end"] = pd.to_datetime(result["period_end"], errors="coerce")
    return result.sort_values("period_end", kind="mergesort").reset_index(drop=True)


def financial_freshness(frame: pd.DataFrame | None, *, filters: FilterState | None = None) -> date | None:
    if frame is None or frame.empty or "period_end" not in frame.columns:
        return None
    selected = apply_filters(frame, _date_filters(filters))
    dates = pd.to_datetime(selected.period_end, errors="coerce").dropna()
    return dates.max().date() if not dates.empty else None


def select_financial_interpretations(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    limit: int = MAX_FINANCIAL_INTERPRETATIONS,
):
    if not isinstance(limit, int) or not 0 <= limit <= MAX_FINANCIAL_INTERPRETATIONS:
        raise ValueError(f"limit must be between 0 and {MAX_FINANCIAL_INTERPRETATIONS}.")
    if frame is None or frame.empty or not {"evidence_type", "business_domain"}.issubset(frame.columns):
        return ()
    financial = frame.loc[frame.business_domain.astype(str).eq("Financial")].copy()
    return select_latest_interpretations(
        financial,
        filters=_date_filters(filters),
        limit=limit,
    )


def select_financial_context(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
) -> tuple[FinancialFact, ...]:
    """Select explicitly allowlisted supporting facts, preserving instant/duration semantics."""
    facts: list[FinancialFact] = []
    for spec in FINANCIAL_CONTEXT:
        rows = _rows(frame, spec, filters)
        if not rows.empty:
            facts.append(_to_fact(rows.iloc[-1], spec))
    return tuple(facts)


def financial_metric_availability(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
) -> tuple[str, ...]:
    return tuple(spec.display_name for spec in FINANCIAL_PRIORITY if _rows(frame, spec, filters).empty)


def financial_period_description(fact: FinancialFact) -> str:
    if fact.period_type == "INSTANT":
        return f"Balance at {format_date(fact.period_end)} · instant"
    start = format_date(fact.period_start) if fact.period_start else "Period start unavailable"
    return f"{start} – {format_date(fact.period_end)} · {fact.period_type.lower()}"


def financial_metric_label(metric_id: str) -> str:
    """Return a business label for allowlisted persisted Financial metrics."""
    return FINANCIAL_LABELS.get(metric_id, "Reported Financial measure")
