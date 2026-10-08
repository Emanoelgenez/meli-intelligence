"""Conservative, auditable SWOT mapping from common Evidence and PESTEL."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

import pandas as pd

from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence
from meli_intelligence.strategy.pestel import validate_pestel, validate_pestel_lineage

METHODOLOGY_VERSION = "1"
SWOT_CATEGORIES = frozenset({"STRENGTH", "WEAKNESS", "OPPORTUNITY", "THREAT"})
INTERNAL_DOMAINS = frozenset({"Financial", "Commerce", "Fintech", "Ecosystem", "Ads", "Logistics"})
SWOT_COLUMNS = [
    "swot_id", "swot_category", "business_domain", "reference_date", "period_start",
    "period_end", "period_type", "entity", "claim", "assessment",
    "classification_rationale", "source_evidence_ids", "source_evidence_types",
    "source_metric_ids", "source_pestel_ids", "source_pestel_dimensions", "source",
    "methodology_version", "definition_context", "scope", "is_interpretation",
]

# A metric is eligible only in its explicitly named internal domain and only
# when its reported numeric direction matches the rule.
_INTERNAL_GROWTH_METRICS = {
    "revenue_yoy_growth": ("Financial", "reported revenue"),
    "net_revenues_financial_income_yoy_growth": ("Financial", "reported revenue and financial income"),
    "gmv_yoy_growth": ("Commerce", "reported GMV"),
    "unique_active_buyers_yoy_growth": ("Commerce", "reported active buyers"),
    "fintech_mau_yoy_growth": ("Fintech", "reported active fintech users"),
    "tpv_yoy_growth": ("Fintech", "reported TPV"),
}
_EXTERNAL_RULES = {
    # Metric, dimension, numeric direction, category, and assessment/rationale
    ("pix_transactions_count_yoy_growth", "TECHNOLOGICAL", 1): (
        "OPPORTUNITY",
        "The reported expansion in national Pix transaction volume is classified under the explicit external digital-payments rule.",
        "Classified from a TECHNOLOGICAL PESTEL item explicitly linked to reported Pix transaction growth.",
    ),
    ("selic_target_change_pp", "ECONOMIC", 1): (
        "THREAT",
        "The reported increase in the Selic target is classified as a change in the external financial environment under the explicit rule.",
        "Classified from an ECONOMIC PESTEL item explicitly linked to a rising Selic target.",
    ),
}
_FORBIDDEN = re.compile(
    r"\b(caused|causes|because of|led to|drives?|explains?|proves?|recommend(?:ation)?|"
    r"should build|must build|feature|solution|product opportunity|product problem|"
    r"causou|causa|por causa de|levou a|explica|prova|recomenda(?:ção)?|"
    r"deveria construir|deve construir|funcionalidade|solução|problema de produto|"
    r"oportunidade de produto)\b",
    re.IGNORECASE,
)


def _json_list(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Lineage fields must contain JSON arrays.") from exc
        if not isinstance(decoded, list):
            raise ValueError("Lineage fields must contain JSON arrays.")
        return [str(item) for item in decoded]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    raise ValueError("Lineage fields must contain JSON arrays.")


def _encode(values) -> str:
    return json.dumps(sorted(set(map(str, values))), ensure_ascii=False, separators=(",", ":"))


def _encode_ordered(values) -> str:
    return json.dumps(list(map(str, values)), ensure_ascii=False, separators=(",", ":"))


def _date_string(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _swot_id(category, assessment, evidence_ids, pestel_ids, reference_date, claim=None) -> str:
    payload = {
        "swot_category": category,
        "assessment": assessment,
        "claim": claim,
        "source_evidence_ids": sorted(map(str, evidence_ids)),
        "source_pestel_ids": sorted(map(str, pestel_ids)),
        "reference_date": _date_string(reference_date),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite_value(row) -> float | None:
    value = row.get("value")
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    return numeric if pd.notna(numeric) and abs(numeric) != float("inf") else None


def _scope(row) -> str:
    return "INTERNAL" if str(row.business_domain) in INTERNAL_DOMAINS else "EXTERNAL"


def _definition_signatures(rows) -> dict[str, set[str]]:
    signatures: dict[str, set[str]] = {}
    token = re.compile(r"\b(definition_version|definition|scope|cohort|population)\s*=\s*([^;|,]+)", re.I)
    for row in rows:
        if str(row.evidence_type) == "INTERPRETATION":
            continue
        for key, value in token.findall(str(row.definition_context or "")):
            signatures.setdefault(key.casefold(), set()).add(value.strip().casefold())
    return signatures


def _assert_temporal_definition_compatibility(rows) -> None:
    metrics = set()
    for row in rows:
        if pd.notna(row.get("metric_id")):
            metrics.add(str(row.get("metric_id")))
        if pd.notna(row.get("source_metric_id")):
            metrics.update(str(row.get("source_metric_id")).split(";"))
    if {"household_free_credit_npl_90d_rate", "npl_15_90_total"}.issubset(metrics):
        raise ValueError("BCB >90-day delinquency and MELI 15-90-day NPL definitions are incompatible.")
    if len(rows) < 2:
        return
    dates = {_date_string(row.reference_date) for row in rows if pd.notna(row.reference_date)}
    if len(dates) > 1:
        raise ValueError("SWOT source evidence periods are incompatible.")
    for column in ("period_type", "period_label"):
        values = {str(row[column]) for row in rows if pd.notna(row[column])}
        if len(values) > 1:
            raise ValueError(f"SWOT source evidence periods are incompatible: {column}.")
    conflicts = {key: values for key, values in _definition_signatures(rows).items() if len(values) > 1}
    if conflicts:
        raise ValueError(f"SWOT source evidence definitions are incompatible: {sorted(conflicts)}.")


def _assert_pestel_period_compatible(pestel_row, evidence_rows) -> None:
    dates = {_date_string(row.reference_date) for row in evidence_rows if pd.notna(row.reference_date)}
    pestel_date = _date_string(pestel_row.get("reference_date"))
    if dates and (len(dates) != 1 or pestel_date not in dates):
        raise ValueError("SWOT Evidence and PESTEL periods are incompatible.")
    if str(pestel_row.get("business_domain")) != str(evidence_rows[0].business_domain):
        raise ValueError("SWOT Evidence and PESTEL business domains are incompatible.")
    for column in ("period_start", "period_end", "period_type", "period_label"):
        values = {
            _date_string(row[column]) if column in {"period_start", "period_end"} else str(row[column])
            for row in evidence_rows if pd.notna(row[column])
        }
        pestel_value = pestel_row.get(column)
        normalized_pestel = (
            _date_string(pestel_value) if column in {"period_start", "period_end"} and pd.notna(pestel_value)
            else str(pestel_value) if pd.notna(pestel_value) else None
        )
        if values and normalized_pestel is not None and (len(values) != 1 or normalized_pestel not in values):
            raise ValueError(f"SWOT Evidence and PESTEL periods are incompatible: {column}.")
    source_signatures = _definition_signatures(evidence_rows)
    token = re.compile(r"\b(definition_version|definition|scope|cohort|population)\s*=\s*([^;|,]+)", re.I)
    pestel_signatures: dict[str, set[str]] = {}
    for key, value in token.findall(str(pestel_row.get("definition_context") or "")):
        pestel_signatures.setdefault(key.casefold(), set()).add(value.strip().casefold())
    if any(key in source_signatures and source_signatures[key] != values for key, values in pestel_signatures.items()):
        raise ValueError("SWOT Evidence and PESTEL definitions are incompatible.")


def _validate_language(frame: pd.DataFrame) -> None:
    for column in ("claim", "assessment", "classification_rationale"):
        for value in frame[column].astype(str):
            if _FORBIDDEN.search(value):
                raise ValueError(f"SWOT {column} contains causal or prescriptive language.")


def validate_swot(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(SWOT_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"SWOT missing columns: {sorted(missing)}")
    result = frame[SWOT_COLUMNS].copy()
    invalid = set(result.swot_category.dropna().astype(str)) - SWOT_CATEGORIES
    if invalid:
        raise ValueError(f"Invalid SWOT categories: {sorted(invalid)}")
    required = [
        "swot_id", "swot_category", "business_domain", "claim", "assessment",
        "classification_rationale", "source_evidence_ids", "source_evidence_types",
        "source_metric_ids", "source_pestel_ids", "source_pestel_dimensions", "source",
        "methodology_version", "definition_context", "scope", "is_interpretation",
    ]
    if result[required].isna().any().any():
        raise ValueError("SWOT required fields cannot be null.")
    if result.swot_id.astype(str).str.strip().eq("").any() or result.swot_id.duplicated(keep=False).any():
        raise ValueError("SWOT IDs must be non-empty and unique.")
    if not result.is_interpretation.astype(bool).all():
        raise ValueError("SWOT classifications must be explicitly marked as interpretations.")
    for _, row in result.iterrows():
        ids = _json_list(row.source_evidence_ids)
        types = _json_list(row.source_evidence_types)
        pestel_ids = _json_list(row.source_pestel_ids)
        dimensions = _json_list(row.source_pestel_dimensions)
        if not ids or len(ids) != len(types):
            raise ValueError("SWOT Evidence lineage must be non-empty and aligned with Evidence types.")
        if len(pestel_ids) != len(dimensions):
            raise ValueError("SWOT PESTEL lineage must be aligned with PESTEL dimensions.")
        external = row.swot_category in {"OPPORTUNITY", "THREAT"}
        if external and (row.scope != "EXTERNAL" or not pestel_ids):
            raise ValueError("External SWOT requires EXTERNAL scope and PESTEL lineage.")
        if not external and (row.scope != "INTERNAL" or pestel_ids):
            raise ValueError("Internal SWOT requires INTERNAL scope and no PESTEL lineage.")
    _validate_language(result)
    for column in ("reference_date", "period_start", "period_end"):
        result[column] = pd.to_datetime(result[column], errors="raise").dt.date
    return result.sort_values(
        ["reference_date", "swot_category", "business_domain", "swot_id"],
        na_position="last", kind="mergesort",
    ).reset_index(drop=True)


def validate_swot_lineage(swot: pd.DataFrame, evidence_registry: pd.DataFrame, pestel=None) -> None:
    evidence = normalize_evidence(evidence_registry)
    known_evidence = set(evidence.evidence_id.astype(str))
    evidence_types = dict(zip(evidence.evidence_id.astype(str), evidence.evidence_type.astype(str)))
    evidence_by_id = {str(row.evidence_id): row for _, row in evidence.iterrows()}
    validated = validate_swot(swot)
    known_pestel: dict[str, pd.Series] = {}
    if pestel is not None:
        from meli_intelligence.strategy.pestel import validate_pestel
        p = validate_pestel(pestel)
        validate_pestel_lineage(p, evidence)
        known_pestel = {str(row.pestel_id): row for _, row in p.iterrows()}
    for _, row in validated.iterrows():
        ids = _json_list(row.source_evidence_ids)
        missing = set(ids) - known_evidence
        if missing:
            raise ValueError(f"Unknown source_evidence_id values: {sorted(missing)}")
        if [evidence_types[eid] for eid in ids] != _json_list(row.source_evidence_types):
            raise ValueError("SWOT source evidence types do not match the Evidence Registry.")
        linked_rows = [evidence_by_id[eid] for eid in ids]
        expected_metrics = sorted({
            metric
            for item in linked_rows
            for metric in (
                str(item.source_metric_id).split(";")
                if pd.notna(item.source_metric_id)
                else [str(item.metric_id)] if pd.notna(item.metric_id) else []
            )
            if metric
        })
        if expected_metrics != _json_list(row.source_metric_ids):
            raise ValueError("SWOT source metric IDs do not match the Evidence Registry.")
        if row.scope == "INTERNAL" and any(str(item.business_domain) not in INTERNAL_DOMAINS for item in linked_rows):
            raise ValueError("Internal SWOT cannot reference external Evidence.")
        if row.scope == "EXTERNAL" and any(str(item.business_domain) in INTERNAL_DOMAINS for item in linked_rows):
            raise ValueError("External SWOT cannot reference internal Evidence.")
        _assert_temporal_definition_compatibility(linked_rows)
        pestel_ids = _json_list(row.source_pestel_ids)
        if pestel_ids and pestel is None:
            raise ValueError("PESTEL dataset is required to validate SWOT PESTEL lineage.")
        unknown_pestel = set(pestel_ids) - set(known_pestel)
        if unknown_pestel:
            raise ValueError(f"Unknown source_pestel_id values: {sorted(unknown_pestel)}")
        pestel_dimensions = _json_list(row.source_pestel_dimensions)
        actual_dimensions = [str(known_pestel[pestel_id].pestel_dimension) for pestel_id in pestel_ids if pestel_id in known_pestel]
        if pestel_ids and actual_dimensions != pestel_dimensions:
            raise ValueError("SWOT PESTEL dimensions do not match their lineage.")
        for pestel_id in pestel_ids:
            pestel_row = known_pestel[pestel_id]
            p_evidence_ids = set(_json_list(pestel_row.source_evidence_ids))
            if not p_evidence_ids or not p_evidence_ids.issubset(set(ids)):
                raise ValueError("SWOT Evidence lineage is incompatible with its PESTEL lineage.")
            p_linked_rows = [evidence_by_id[eid] for eid in sorted(p_evidence_ids)]
            _assert_temporal_definition_compatibility(p_linked_rows)
            _assert_pestel_period_compatible(pestel_row, p_linked_rows)


def _eligible_internal(row):
    spec = _INTERNAL_GROWTH_METRICS.get(str(row.metric_id))
    value = _finite_value(row)
    if spec is None or str(row.business_domain) != spec[0] or value is None:
        return None
    kind = str(row.claim_kind).casefold()
    if value > 0 and kind in {"growth", "increase", "yoy_growth"}:
        return "STRENGTH", f"The reported expansion in {spec[1]} is classified as an internal strength under the explicit metric allowlist."
    if value < 0 and kind in {"decrease", "yoy_decline"}:
        return "WEAKNESS", f"The reported contraction in {spec[1]} is classified as an internal weakness under the explicit metric allowlist."
    return None


def _eligible_external(row):
    if str(row.business_domain) != "Macro":
        return None
    value = _finite_value(row)
    if value is None:
        return None
    for (metric, dimension, sign), result in _EXTERNAL_RULES.items():
        if str(row.metric_id) == metric and value * sign > 0:
            if metric == "pix_transactions_count_yoy_growth" and str(row.claim_kind) not in {"growth", "increase", "yoy_growth", "technology_adoption", "digital_payment_adoption"}:
                continue
            if metric == "selic_target_change_pp" and str(row.claim_kind) not in {"increase", "rising"}:
                continue
            return dimension, result
    return None


def build_swot(evidence_registry: pd.DataFrame, pestel=None) -> pd.DataFrame:
    """Apply only the documented internal and externally PESTEL-linked rules."""
    evidence = normalize_evidence(evidence_registry)
    evidence_ids = set(evidence.evidence_id.astype(str))
    evidence_by_id = {str(row.evidence_id): row for _, row in evidence.iterrows()}
    p_rows = []
    if pestel is not None:
        p = validate_pestel(pestel)
        validate_pestel_lineage(p, evidence)
        p_rows = p.to_dict("records")
    output = []
    for _, row in evidence.iterrows():
        upstream = _json_list(row.source_evidence_ids)
        unknown = set(upstream) - evidence_ids
        if unknown:
            raise ValueError(f"Unknown source_evidence_id values: {sorted(unknown)}")
        ids = sorted({str(row.evidence_id), *upstream})
        linked_rows = [evidence_by_id[eid] for eid in ids]
        _assert_temporal_definition_compatibility(linked_rows)
        scope = _scope(row)
        if scope == "INTERNAL":
            eligible = _eligible_internal(row)
            if eligible is None:
                continue
            category, assessment = eligible
            rationale = "Classified from an INTERNAL company metric in the explicit metric/domain/direction allowlist."
            p_matches = []
        else:
            external = _eligible_external(row)
            if external is None:
                continue
            dimension, (category, assessment, rationale) = external
            candidates = []
            for item in p_rows:
                p_ids = set(_json_list(item["source_evidence_ids"]))
                if str(row.evidence_id) not in p_ids:
                    continue
                p_metrics = set(_json_list(item["source_metric_ids"]))
                source_metrics = {str(row.metric_id)}
                if pd.notna(row.source_metric_id):
                    source_metrics.update(str(row.source_metric_id).split(";"))
                if not p_metrics:
                    for linked_id in p_ids:
                        linked = evidence_by_id[linked_id]
                        if pd.notna(linked.source_metric_id):
                            source_metrics.update(str(linked.source_metric_id).split(";"))
                        elif pd.notna(linked.metric_id):
                            source_metrics.add(str(linked.metric_id))
                if not (p_metrics & source_metrics):
                    raise ValueError("SWOT Evidence/PESTEL metric lineage is incompatible.")
                p_linked_rows = [evidence_by_id[eid] for eid in sorted(p_ids)]
                _assert_temporal_definition_compatibility(p_linked_rows)
                _assert_pestel_period_compatible(item, p_linked_rows)
                if str(item["pestel_dimension"]) == dimension:
                    candidates.append(item)
            if not candidates:
                raise ValueError("External SWOT classification requires compatible PESTEL lineage.")
            p_matches = sorted(candidates, key=lambda item: str(item["pestel_id"]))
            ids = sorted({eid for item in p_matches for eid in _json_list(item["source_evidence_ids"])})
            linked_rows = [evidence_by_id[eid] for eid in ids]
            _assert_temporal_definition_compatibility(linked_rows)
        if scope == "INTERNAL" and p_matches:
            raise ValueError("Internal SWOT cannot include PESTEL lineage.")
        p_ids = [str(item["pestel_id"]) for item in p_matches]
        p_dimensions = [str(item["pestel_dimension"]) for item in p_matches]
        linked_types = [str(evidence_by_id[eid].evidence_type) for eid in ids]
        linked_metrics = sorted({
            metric
            for eid in ids
            for metric in (
                str(evidence_by_id[eid].source_metric_id).split(";")
                if pd.notna(evidence_by_id[eid].source_metric_id)
                else [str(evidence_by_id[eid].metric_id)] if pd.notna(evidence_by_id[eid].metric_id) else []
            )
            if metric
        })
        sources = sorted({str(evidence_by_id[eid].source) for eid in ids})
        context = ";".join(sorted({str(evidence_by_id[eid].definition_context) for eid in ids}))
        if scope == "EXTERNAL" and str(row.metric_id) == "selic_target_change_pp":
            context += ";external_financial_environment;not_company_performance"
        elif scope == "EXTERNAL" and str(row.metric_id) == "pix_transactions_count_yoy_growth":
            context += ";national_digital_payment_context;not_company_performance"
        output.append({
            "swot_id": _swot_id(category, assessment, ids, p_ids, row.reference_date, str(row.claim)),
            "swot_category": category,
            "business_domain": row.business_domain,
            "reference_date": row.reference_date,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "period_type": row.period_type,
            "entity": row.entity,
            "claim": str(row.claim),
            "assessment": assessment,
            "classification_rationale": rationale,
            "source_evidence_ids": _encode_ordered(ids),
            "source_evidence_types": _encode_ordered(linked_types),
            "source_metric_ids": _encode(linked_metrics),
            "source_pestel_ids": _encode_ordered(p_ids),
            "source_pestel_dimensions": _encode_ordered(p_dimensions),
            "source": ";".join(sources),
            "methodology_version": METHODOLOGY_VERSION,
            "definition_context": context,
            "scope": scope,
            "is_interpretation": True,
        })
    result = pd.DataFrame(output, columns=SWOT_COLUMNS)
    if result.empty:
        return result
    result = validate_swot(result)
    validate_swot_lineage(result, evidence, p if pestel is not None else None)
    return result
