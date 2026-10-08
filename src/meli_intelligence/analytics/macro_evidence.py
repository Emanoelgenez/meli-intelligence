"""Deterministic, source-grounded Macro FACT to OBSERVATION mapping."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from typing import Any

import pandas as pd


METHODOLOGY_VERSION = "1"
MACRO_EVIDENCE_COLUMNS = [
    "evidence_id", "evidence_type", "business_domain", "metric_id",
    "reference_date", "claim", "claim_kind", "source", "source_metric_id",
    "is_interpretation", "definition_context", "analytics_kind",
    "methodology_version",
]

FACT_LABELS = {
    "selic_target_annual": "Meta Selic",
    "selic_effective_annual_252": "Selic efetiva anualizada em base 252",
    "ipca_monthly_change": "IPCA mensal",
    "ipca_12m_change": "IPCA acumulado em 12 meses",
    "usd_brl_sell_rate": "Cotação diária de venda USD/BRL",
    "household_free_credit_balance": "Saldo de crédito livre para pessoas físicas",
    "household_free_credit_npl_90d_rate": "Inadimplência BCB de crédito livre PF acima de 90 dias",
    "ibc_br_activity_sa_index": "Índice de atividade econômica IBC-Br com ajuste sazonal",
    "unemployment_rate_rolling_3m": "Taxa de desocupação do trimestre móvel de três meses",
    "retail_sales_volume_mom_sa": "Variação mensal dessazonalizada do volume de vendas no varejo",
    "pix_transactions_count_monthly": "Quantidade mensal de transações Pix",
    "pix_transactions_value_monthly": "Valor mensal de transações Pix",
}

DERIVED_CLAIMS = {
    "selic_target_change_pp": (
        "Meta Selic", "p.p.", "change"
    ),
    "ipca_12m_change_pp": (
        "IPCA acumulado em 12 meses", "p.p.", "inflation"
    ),
    "usd_brl_monthly_change_pct": (
        "Cotação USD/BRL", "%", "change"
    ),
    "household_free_credit_balance_yoy_growth": (
        "Saldo de crédito livre PF", "%", "growth"
    ),
    "household_free_credit_npl_90d_yoy_change_pp": (
        "Inadimplência BCB de crédito livre PF acima de 90 dias", "p.p.", "change"
    ),
    "ibc_br_activity_mom_change_pct": (
        "Atividade econômica medida pelo IBC-Br com ajuste sazonal", "%", "change"
    ),
    "unemployment_rate_change_pp": (
        "Taxa de desocupação do trimestre móvel de três meses", "p.p.", "change"
    ),
    "pix_transactions_count_yoy_growth": (
        "Quantidade mensal de transações Pix", "%", "growth"
    ),
    "pix_transactions_value_yoy_growth": (
        "Valor mensal de transações Pix", "%", "growth"
    ),
}


def _number(value: float) -> str:
    if not math.isfinite(float(value)):
        raise ValueError("Macro observation value must be finite.")
    return f"{float(value):.15g}".replace(".", ",")


def _month(value: date) -> str:
    return value.strftime("%m/%Y")


def _claim_kind_for_change(value: float, *, inflation: bool = False, growth: bool = False) -> tuple[str, str]:
    if value == 0:
        return "unchanged", "permaneceu sem variação"
    if inflation:
        return ("acceleration", "acelerou") if value > 0 else ("deceleration", "desacelerou")
    if growth:
        return ("yoy_growth", "aumentou") if value > 0 else ("yoy_decline", "diminuiu")
    return ("increase", "aumentou") if value > 0 else ("decrease", "diminuiu")


def _fact_claim(row: dict[str, Any]) -> tuple[str, str]:
    metric_id = str(row["metric_id"])
    value = float(row["value"])
    unit = str(row["unit"])
    reference = row["reference_date"]
    label = FACT_LABELS.get(metric_id, metric_id.replace("_", " "))
    if unit in {"percent", "percent_per_year"}:
        suffix = "% ao ano" if unit == "percent_per_year" else "%"
    elif unit == "million_brl":
        suffix = " milhões de BRL"
    elif unit == "brl_per_usd":
        suffix = " BRL por USD"
    elif unit == "transactions":
        suffix = " transações"
    elif unit == "brl":
        suffix = " BRL"
    else:
        suffix = f" {unit}"
    if metric_id == "usd_brl_sell_rate":
        claim = f"{label} foi {_number(value)}{suffix} em {reference.isoformat()}."
    else:
        claim = f"{label} foi {_number(value)}{suffix} no período {_month(reference)}."
    return claim, "level"


def _analytics_claim(row: dict[str, Any]) -> tuple[str, str]:
    metric_id = str(row["metric_id"])
    value = float(row["value"])
    reference = row["reference_date"]
    label, unit, kind = DERIVED_CLAIMS.get(metric_id, (metric_id.replace("_", " "), str(row["unit"]), "change"))
    claim_kind, verb = _claim_kind_for_change(
        value, inflation=kind == "inflation", growth=kind == "growth"
    )
    number = _number(abs(value)) if value != 0 else _number(value)
    if metric_id == "usd_brl_month_end":
        observation_date = row.get("source_reference_date")
        if observation_date is None or pd.isna(observation_date):
            observation_date = reference
        return (
            f"A cotação diária de venda USD/BRL observada em {observation_date.isoformat()}, "
            f"último registro disponível do mês, foi {_number(value)} BRL por USD.",
            "level",
        )
    if metric_id == "selic_target_change_pp":
        claim = f"A Meta Selic {verb} {number} p.p. em relação à observação anterior em {_month(reference)}."
    elif metric_id == "ipca_12m_change_pp":
        claim = f"O IPCA acumulado em 12 meses {verb} {number} p.p. ante o mês anterior em {_month(reference)}."
    elif metric_id == "usd_brl_monthly_change_pct":
        claim = f"A cotação USD/BRL {verb} {number}% ante o mês anterior em {_month(reference)}."
    elif metric_id == "household_free_credit_balance_yoy_growth":
        claim = f"O saldo de crédito livre PF {verb} {number}% ante o mesmo mês do ano anterior em {_month(reference)}."
    elif metric_id == "household_free_credit_npl_90d_yoy_change_pp":
        claim = f"A inadimplência BCB de crédito livre PF acima de 90 dias {verb} {number} p.p. ante o mesmo mês do ano anterior em {_month(reference)}."
    elif metric_id == "ibc_br_activity_mom_change_pct":
        claim = f"A atividade econômica medida pelo IBC-Br com ajuste sazonal {verb} {number}% ante o mês anterior em {_month(reference)}."
    elif metric_id == "unemployment_rate_change_pp":
        claim = f"A taxa de desocupação do trimestre móvel de três meses {verb} {number} p.p. ante a publicação anterior em {_month(reference)}."
    elif metric_id == "pix_transactions_count_yoy_growth":
        claim = f"A quantidade mensal de transações Pix {verb} {number}% ante o mesmo mês do ano anterior em {_month(reference)}."
    elif metric_id == "pix_transactions_value_yoy_growth":
        claim = f"O valor mensal de transações Pix {verb} {number}% ante o mesmo mês do ano anterior em {_month(reference)}."
    else:
        claim = f"{label} {verb} {number} {unit} no período {_month(reference)}."
    return claim, claim_kind


def _evidence_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_macro_observations(
    macro_facts: pd.DataFrame,
    macro_analytics: pd.DataFrame,
) -> pd.DataFrame:
    """Create one deterministic OBSERVATION for each official or derived fact."""
    fact_required = {"metric_id", "reference_date", "value", "unit", "source"}
    analytics_required = {
        "metric_id", "reference_date", "value", "unit", "source_metric_id",
        "source", "analytics_kind", "definition_context",
    }
    missing_facts = fact_required.difference(macro_facts.columns)
    missing_analytics = analytics_required.difference(macro_analytics.columns)
    if missing_facts:
        raise ValueError(f"Macro facts missing columns: {sorted(missing_facts)}")
    if missing_analytics:
        raise ValueError(f"Macro analytics missing columns: {sorted(missing_analytics)}")
    facts = macro_facts.copy()
    analytics = macro_analytics.copy()
    facts["reference_date"] = pd.to_datetime(facts.reference_date).dt.date
    analytics["reference_date"] = pd.to_datetime(analytics.reference_date).dt.date
    if facts[["metric_id", "reference_date", "value", "unit", "source"]].isna().any().any():
        raise ValueError("Macro facts for observations cannot contain null required values.")
    if analytics[list(analytics_required)].isna().any().any():
        raise ValueError("Macro analytics for observations cannot contain null required values.")
    if facts.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro fact economic key in observations.")
    if analytics.duplicated(["metric_id", "reference_date"], keep=False).any():
        raise ValueError("Duplicate macro analytics economic key in observations.")
    for name, frame in (("fact", facts), ("analytics", analytics)):
        numeric_values = pd.to_numeric(frame["value"], errors="raise")
        if numeric_values.isna().any() or not numeric_values.map(
            lambda value: math.isfinite(float(value))
        ).all():
            raise ValueError(f"Macro {name} observations must have finite values.")
    rows: list[dict[str, Any]] = []
    for row in facts.to_dict(orient="records"):
        claim, claim_kind = _fact_claim(row)
        source_metric_id = str(row["metric_id"])
        evidence_payload = {
            "evidence_type": "OBSERVATION", "metric_id": source_metric_id,
            "reference_date": row["reference_date"].isoformat(), "claim": claim,
            "source_metric_id": source_metric_id, "source": str(row["source"]),
        }
        rows.append({
            "evidence_id": _evidence_id(evidence_payload),
            "evidence_type": "OBSERVATION", "business_domain": "Macro",
            "metric_id": source_metric_id, "reference_date": row["reference_date"],
            "claim": claim, "claim_kind": claim_kind, "source": str(row["source"]),
            "source_metric_id": source_metric_id, "is_interpretation": False,
            "definition_context": "reported_macro_fact;source_value_preserved",
            "analytics_kind": "reported_fact", "methodology_version": METHODOLOGY_VERSION,
        })
    for row in analytics.to_dict(orient="records"):
        claim, claim_kind = _analytics_claim(row)
        source_metric_id = str(row["source_metric_id"])
        evidence_payload = {
            "evidence_type": "OBSERVATION", "metric_id": str(row["metric_id"]),
            "reference_date": row["reference_date"].isoformat(), "claim": claim,
            "source_metric_id": source_metric_id,
            "source": str(row["source"]),
            "definition_context": str(row["definition_context"]),
        }
        rows.append({
            "evidence_id": _evidence_id(evidence_payload),
            "evidence_type": "OBSERVATION", "business_domain": "Macro",
            "metric_id": str(row["metric_id"]), "reference_date": row["reference_date"],
            "claim": claim, "claim_kind": claim_kind,
            "source": str(row["source"]),
            "source_metric_id": source_metric_id, "is_interpretation": False,
            "definition_context": str(row["definition_context"]),
            "analytics_kind": str(row["analytics_kind"]),
            "methodology_version": METHODOLOGY_VERSION,
        })
    result = pd.DataFrame(rows, columns=MACRO_EVIDENCE_COLUMNS)
    if result.evidence_id.duplicated().any():
        raise ValueError("Duplicate Macro evidence identity.")
    return result.sort_values(["reference_date", "metric_id", "evidence_id"]).reset_index(drop=True)
