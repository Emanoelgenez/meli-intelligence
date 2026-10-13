"""Pure presentation models and formatters for executive-level evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping

import pandas as pd

from meli_intelligence.ui.filters import FilterState, apply_filters

MAX_EXECUTIVE_SIGNALS = 4
MAX_INTERPRETATIONS = 3
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

DOMAIN_LABELS = {
    "Financial": "Financeiro",
    "Commerce": "Comércio",
    "Fintech": "Serviços financeiros",
    "Macro": "Macro",
    "Market": "Mercado",
    "Ecosystem": "Ecossistema",
    "Ads": "Anúncios",
    "Logistics": "Logística",
}


def display_domain(domain: str | None) -> str:
    return DOMAIN_LABELS.get(domain, domain or "Não informado")


def format_quarter(value: object) -> str:
    try:
        parsed = pd.Timestamp(value)
        if pd.isna(parsed):
            return "Indisponível"
        return f"{(parsed.month - 1) // 3 + 1}º tri. {parsed.year}"
    except (TypeError, ValueError, OverflowError):
        return "Indisponível"


def format_period_label(
    period_type: str | None, period_end: object, label: object = None
) -> str:
    kind = str(period_type or "").upper()
    if kind in {"QUARTER", "INSTANT"}:
        return format_quarter(period_end)
    if kind == "FY":
        try:
            return f"Exercício de {pd.Timestamp(period_end).year}"
        except (TypeError, ValueError, OverflowError):
            return "Exercício fiscal"
    if kind == "YTD":
        return f"Acumulado até {format_date_br(period_end)}"
    return (
        str(label).strip()
        if label is not None and str(label).strip()
        else format_date_br(period_end)
    )


@dataclass(frozen=True)
class ExecutiveSignal:
    metric_id: str
    display_name: str
    business_domain: str
    value: float
    formatted_value: str
    unit: str
    reference_date: date
    period_label: str
    source: str
    full_precision_value: str
    context: str


@dataclass(frozen=True)
class InterpretationPreview:
    evidence_id: str
    claim: str
    metric_id: str
    source: str
    reference_date: date


@dataclass(frozen=True)
class ExecutiveSummary:
    available_count: int
    dataset_count: int
    missing_count: int
    empty_count: int
    invalid_count: int
    latest_reference_date: date | None

    @property
    def degraded(self) -> bool:
        return bool(self.missing_count or self.empty_count or self.invalid_count)


# Labels are a small presentation allowlist; values always come from source frames.
_SIGNAL_CANDIDATES = (
    (
        "financial_facts",
        "Financial",
        (
            (
                "net_revenues_financial_income",
                "Receita e resultado financeiro",
                "Receita reportada no trimestre.",
            ),
        ),
    ),
    (
        "operational_kpis",
        "Commerce",
        (
            (
                "gmv",
                "Volume bruto de mercadorias (GMV)",
                "Volume de comércio reportado.",
            ),
            (
                "unique_active_buyers",
                "Compradores ativos únicos",
                "Compradores de comércio reportados.",
            ),
        ),
    ),
    (
        "operational_kpis",
        "Fintech",
        (
            (
                "fintech_mau",
                "Usuários ativos mensais (Fintech)",
                "Base reportada de usuários ativos do Fintech.",
            ),
            (
                "tpv",
                "Volume total de pagamentos (TPV)",
                "Volume de pagamentos reportado.",
            ),
        ),
    ),
    (
        "macro_indicators",
        "Macro",
        (
            (
                "selic_target_annual",
                "Meta da taxa Selic",
                "Taxa oficial de referência da política monetária.",
            ),
            (
                "ipca_12m_change",
                "IPCA em 12 meses",
                "Inflação oficial acumulada em 12 meses.",
            ),
            (
                "pix_transactions_count_monthly",
                "Transações Pix mensais",
                "Quantidade mensal de transações Pix reportada pelo Banco Central.",
            ),
        ),
    ),
)


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _localized_number(value: float, decimals: int) -> str:
    rendered = f"{value:,.{decimals}f}"
    return rendered.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_compact_number(value: object) -> str:
    number = _number(value)
    if number is None:
        return "Indisponível"
    magnitude = abs(number)
    for threshold, suffix in (
        (1_000_000_000_000, "tri"),
        (1_000_000_000, "bi"),
        (1_000_000, "milhões"),
    ):
        if magnitude >= threshold:
            scaled = number / threshold
            decimals = 0 if scaled.is_integer() else 2
            return f"{_localized_number(scaled, decimals)} {suffix}"
    decimals = 0 if number.is_integer() else 2
    return _localized_number(number, decimals)


def format_count(value: object, noun: str | None = None) -> str:
    """Format reported counts consistently for pt-BR dashboard labels."""
    number = _number(value)
    if number is None:
        return "Indisponível"
    compact = format_compact_number(number)
    if not noun:
        return compact
    if abs(number) >= 1_000_000:
        if compact.endswith(" milhões") and abs(number) == 1_000_000:
            compact = compact.removesuffix("s")
        return f"{compact} de {noun}"
    singular = {
        "itens": "item",
        "transações": "transação",
        "usuários": "usuário",
    }.get(noun, noun)
    label = singular if abs(number) == 1 else noun
    return f"{compact} {label}"


def _compact_currency(value: float) -> str:
    magnitude = abs(value)
    for threshold, suffix in (
        (1_000_000_000_000, "tri"),
        (1_000_000_000, "bi"),
        (1_000_000, "mi"),
    ):
        if magnitude >= threshold:
            scaled = value / threshold
            decimals = 0 if scaled.is_integer() else 2
            return f"{_localized_number(scaled, decimals)} {suffix}"
    return _localized_number(value, 0 if value.is_integer() else 2)


def format_unit(unit: str | None) -> str:
    if not unit:
        return "unidade não informada"
    return {
        "percent": "%",
        "percentage_points": "p.p.",
        "USD": "US$",
        "BRL": "R$",
        "brl": "R$",
        "million_usd": "milhões de US$",
        "million_brl": "milhões de R$",
        "brl_per_usd": "R$ por US$",
        "count": "",
        "transactions": "transações",
        "users": "usuários",
        "index": "pontos de índice",
    }.get(unit, unit.replace("_", " "))


def format_metric(value: object, unit: str | None, *, compact: bool = True) -> str:
    number = _number(value)
    if number is None:
        return "Indisponível"
    if unit == "million_usd":
        divisor, suffix = (1_000, "bi") if abs(number) >= 1_000 else (1, "mi")
        scaled = number / divisor
        decimals = 0 if scaled.is_integer() else 2
        return f"US$ {_localized_number(scaled, decimals)} {suffix}"
    if unit == "million_brl":
        divisor, suffix = (1_000, "bi") if abs(number) >= 1_000 else (1, "mi")
        scaled = number / divisor
        decimals = 0 if scaled.is_integer() else 2
        return f"R$ {_localized_number(scaled, decimals)} {suffix}"
    if unit == "count":
        return format_count(number) if compact else _localized_number(
            number, 0 if number.is_integer() else 2
        )
    if unit == "users":
        if compact:
            return format_count(number, "usuários")
        return f"{_localized_number(number, 0 if number.is_integer() else 2)} usuários"
    magnitude = abs(number)
    is_currency = unit in {"USD", "BRL", "brl"}
    if compact and is_currency and magnitude >= 1_000_000:
        rendered = _compact_currency(number)
    else:
        decimals = 0 if number.is_integer() and unit in {"transactions", "users"} else 2
        rendered = _localized_number(number, decimals)
    if unit == "percent":
        return f"{rendered}%"
    if unit == "percentage_points":
        return f"{rendered} p.p."
    if unit == "USD":
        return f"US$ {rendered}"
    if unit in {"BRL", "brl"}:
        return f"R$ {rendered}"
    if unit == "brl_per_usd":
        return f"R$ {rendered} / US$"
    if unit == "transactions":
        return f"{rendered} {format_unit(unit)}"
    return f"{rendered} {format_unit(unit)}"


def format_date(value: object) -> str:
    if value is None:
        return "Unavailable"
    try:
        if pd.isna(value):
            return "Unavailable"
        parsed = pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return "Unavailable"
    return f"{parsed.day:02d} {_MONTHS[parsed.month - 1]} {parsed.year}"


def format_date_br(value: object) -> str:
    if value is None:
        return "Indisponível"
    try:
        if pd.isna(value):
            return "Indisponível"
        parsed = pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return "Indisponível"
    return parsed.strftime("%d/%m/%Y")


def format_status(status: str) -> str:
    return {
        "AVAILABLE": "Disponível — arquivo legível",
        "MISSING": "Indisponível — arquivo não encontrado",
        "EMPTY": "Indisponível — sem observações",
        "INVALID": "Indisponível — arquivo inválido ou ilegível",
    }.get(status, "Indisponível — motivo não informado")


def executive_summary(health_records) -> ExecutiveSummary:
    dates = [
        record.latest_reference_date
        for record in health_records
        if record.latest_reference_date is not None
    ]
    counts = {
        status: sum(record.status == status for record in health_records)
        for status in ("AVAILABLE", "MISSING", "EMPTY", "INVALID")
    }
    return ExecutiveSummary(
        available_count=counts["AVAILABLE"],
        dataset_count=len(health_records),
        missing_count=counts["MISSING"],
        empty_count=counts["EMPTY"],
        invalid_count=counts["INVALID"],
        latest_reference_date=max(dates) if dates else None,
    )


def latest_global_reference_date(health_records) -> date | None:
    return executive_summary(health_records).latest_reference_date


def _date_for_row(row: pd.Series) -> date | None:
    for column in ("reference_date", "period_end", "date"):
        if column in row.index and pd.notna(row[column]):
            try:
                return pd.Timestamp(row[column]).date()
            except (TypeError, ValueError, OverflowError):
                return None
    return None


def _period_label(row: pd.Series, reference_date: date) -> str:
    for column in ("period_label", "period"):
        if column in row.index and pd.notna(row[column]) and str(row[column]).strip():
            return str(row[column])
    return format_date_br(reference_date)


def _row_text(row: pd.Series, column: str, fallback: str) -> str:
    value = row.get(column)
    if value is None or pd.isna(value) or not str(value).strip():
        return fallback
    return str(value)


def _candidate_rows(
    frame: pd.DataFrame, metric_id: str, filters: FilterState
) -> pd.DataFrame:
    if (
        frame is None
        or frame.empty
        or "metric_id" not in frame.columns
        or "value" not in frame.columns
    ):
        return pd.DataFrame()
    result = apply_filters(frame, filters)
    result = result.loc[result.metric_id.astype(str) == metric_id].copy()
    if metric_id == "net_revenues_financial_income" and "period_type" in result.columns:
        quarters = result.loc[result.period_type.astype(str).str.upper() == "QUARTER"]
        if not quarters.empty:
            result = quarters.copy()
    result["_ui_date"] = result.apply(_date_for_row, axis=1)
    result = result.loc[result._ui_date.notna()].copy()
    if result.empty:
        return result
    result["_ui_filed"] = (
        pd.to_datetime(result["filed_at"], errors="coerce")
        if "filed_at" in result.columns
        else pd.NaT
    )
    return result.sort_values(
        ["_ui_date", "_ui_filed"], kind="mergesort", na_position="first"
    )


def select_executive_signals(
    dataset_frames: Mapping[str, pd.DataFrame | None],
    *,
    filters: FilterState | None = None,
    max_signals: int = MAX_EXECUTIVE_SIGNALS,
) -> tuple[ExecutiveSignal, ...]:
    """Select the latest reported fact per domain; calculate nothing."""
    if (
        not isinstance(max_signals, int)
        or max_signals < 0
        or max_signals > MAX_EXECUTIVE_SIGNALS
    ):
        raise ValueError(f"max_signals must be between 0 and {MAX_EXECUTIVE_SIGNALS}.")
    state = (filters or FilterState()).validate()
    signals = []
    for dataset_id, domain, candidates in _SIGNAL_CANDIDATES:
        if state.business_domain is not None and state.business_domain != domain:
            continue
        frame = dataset_frames.get(dataset_id)
        selected = None
        selected_metric = None
        selected_label = None
        selected_context = None
        for metric_id, label, context in candidates:
            rows = _candidate_rows(frame, metric_id, state)
            if not rows.empty:
                selected = rows.iloc[-1]
                selected_metric, selected_label, selected_context = (
                    metric_id,
                    label,
                    context,
                )
                break
        if selected is None or len(signals) >= max_signals:
            continue
        value = _number(selected.get("value"))
        reference_date = selected.get("_ui_date")
        if value is None or reference_date is None:
            continue
        unit = _row_text(selected, "unit", "")
        source = _row_text(selected, "source", "Fonte não informada")
        signals.append(
            ExecutiveSignal(
                metric_id=selected_metric,
                display_name=selected_label,
                business_domain=domain,
                value=value,
                formatted_value=format_metric(value, unit),
                unit=format_unit(unit),
                reference_date=reference_date,
                period_label=format_period_label(
                    str(selected.get("period_type", "")),
                    reference_date,
                    _period_label(selected, reference_date),
                ),
                source=source,
                full_precision_value=(
                    f"{selected.get('value')} {format_unit(unit)}".strip()
                ),
                context=selected_context,
            )
        )
    return tuple(signals)


def select_latest_interpretations(
    frame: pd.DataFrame | None,
    *,
    filters: FilterState | None = None,
    limit: int = MAX_INTERPRETATIONS,
) -> tuple[InterpretationPreview, ...]:
    if not isinstance(limit, int) or limit < 0 or limit > MAX_INTERPRETATIONS:
        raise ValueError(f"limit must be between 0 and {MAX_INTERPRETATIONS}.")
    if frame is None or frame.empty or "evidence_type" not in frame.columns:
        return ()
    state = (filters or FilterState()).validate()
    selected = apply_filters(frame, state)
    selected = selected.loc[
        selected.evidence_type.astype(str) == "INTERPRETATION"
    ].copy()
    if selected.empty:
        return ()
    selected["_ui_date"] = selected.apply(_date_for_row, axis=1)
    selected = selected.loc[selected._ui_date.notna()].sort_values(
        ["_ui_date", "evidence_id"], ascending=[False, True], kind="mergesort"
    )
    results = []
    for _, row in selected.head(limit).iterrows():
        metric_id = _row_text(
            row,
            "source_metric_id",
            _row_text(row, "metric_id", "Métrica não informada"),
        )
        results.append(
            InterpretationPreview(
                evidence_id=str(row.get("evidence_id", "")),
                claim=str(row.get("claim", "")),
                metric_id=str(metric_id),
                source=_row_text(row, "source", "Fonte não informada"),
                reference_date=row["_ui_date"],
            )
        )
    return tuple(results)


def product_evidence_counts(frame: pd.DataFrame | None) -> dict[str, int]:
    if frame is None or frame.empty or "product_evidence_type" not in frame.columns:
        return {"hypotheses": 0, "questions": 0}
    values = frame.product_evidence_type.astype(str)
    return {
        "hypotheses": int(values.eq("HYPOTHESIS").sum()),
        "questions": int(values.eq("QUESTION_FOR_PRODUCT_DISCOVERY").sum()),
    }


def degraded_state_message(health_records) -> str | None:
    invalid = sum(record.status == "INVALID" for record in health_records)
    missing = sum(record.status == "MISSING" for record in health_records)
    empty = sum(record.status == "EMPTY" for record in health_records)
    parts = []
    if invalid:
        parts.append(f"{invalid} conjunto(s) ilegível(is)")
    if missing:
        parts.append(f"{missing} conjunto(s) ainda indisponível(is)")
    if empty:
        parts.append(f"{empty} conjunto(s) sem observações")
    return (
        "Disponibilidade de dados limitada: "
        + "; ".join(parts)
        + ". Consulte Fontes e qualidade dos dados."
        if parts
        else None
    )


def unavailable_message(
    label: str, status: str, *, boundary: str, reason: str | None = None
) -> str:
    """Describe an existing unavailable state without inferring data or its cause."""
    reasons = {
        "MISSING": "No local dataset is available for this view.",
        "EMPTY": "The dataset is readable but contains no observations.",
        "INVALID": "The data could not be read or validated for this view.",
        "UNAVAILABLE": "No eligible data is available for this view.",
    }
    explanation = reason or reasons.get(
        status, "An unavailability reason was not reported."
    )
    return (
        f"{label}: {status}. {explanation} {boundary} "
        "See Data Quality & Sources for details."
    )
