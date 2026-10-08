"""Deterministic Product hypotheses and discovery questions from linked Evidence."""
from __future__ import annotations

import hashlib
import json
import re

import pandas as pd

from meli_intelligence.evidence.model import EVIDENCE_TYPES, normalize_evidence
from meli_intelligence.strategy.pestel import validate_pestel, validate_pestel_lineage
from meli_intelligence.strategy.swot import validate_swot, validate_swot_lineage

METHODOLOGY_VERSION = "1"
PRODUCT_EVIDENCE_TYPES = frozenset({"HYPOTHESIS", "QUESTION_FOR_PRODUCT_DISCOVERY"})
DISCOVERY_THEMES = frozenset({"ECOSYSTEM_ENGAGEMENT"})
PRODUCT_EVIDENCE_COLUMNS = [
    "product_evidence_id", "product_evidence_type", "discovery_theme", "business_domain",
    "reference_date", "period_start", "period_end", "period_type", "entity", "statement",
    "rationale", "source_evidence_ids", "source_interpretation_ids", "source_pestel_ids",
    "source_swot_ids", "source_hypothesis_ids", "source_metric_ids", "source",
    "methodology_version", "definition_context", "scope",
]

_COMMERCE_METRICS = frozenset({"unique_active_buyers_yoy_growth", "gmv_yoy_growth"})
_FINTECH_METRICS = frozenset({"fintech_mau_yoy_growth", "tpv_yoy_growth"})
_EVIDENCE_PRIORITY = {"FACT": 1, "OBSERVATION": 2, "INTERPRETATION": 3}
_HYPOTHESIS_STATEMENT = (
    "Reported aggregate Commerce and Fintech activity may correspond to distinct cross-domain "
    "ecosystem engagement patterns; the available aggregates do not establish user-level overlap, "
    "so the relationship requires user-level validation."
)
_HYPOTHESIS_RATIONALE = (
    "Generated from temporally and definition-compatible Commerce and Fintech Evidence. "
    "Aggregate metrics do not identify the same users across domains; user-level validation is "
    "required before making claims about cross-domain engagement."
)
_QUESTION_STATEMENT = (
    "How do engagement patterns differ among users active in Commerce, in Fintech, and in both "
    "domains, if user-level overlap is present?"
)
_QUESTION_RATIONALE = (
    "This open question is intended to validate or qualify the linked hypothesis without assuming "
    "that cross-domain overlap exists or that a Product problem is present."
)
_LANGUAGE_GUARD = re.compile(
    r"\b(caused|causes|because of|led to|drives?|proves?|guarantees?|will increase|will improve|"
    r"recommend(?:ation)?|should build|must build|feature|solution|roadmap|prioriti[sz]e|"
    r"launch|cashback|rewards?|loyalty(?: program)?|users?\s+(?:want|need)|customers?\s+(?:want|need)|"
    r"causou|causa|por causa de|levou a|explica|prova|garante|vai aumentar|vai melhorar|"
    r"recomenda(?:ção)?|deveria construir|deve construir|funcionalidade|solução|roteiro|"
    r"priorize|lançar|recompensa|programa de fidelidade|usuários?\s+(?:querem|precisam)|"
    r"clientes?\s+(?:querem|precisam)\b)",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(r"^(how|what|which|where|when|to what extent)\b", re.IGNORECASE)
_UNCERTAINTY = re.compile(r"\b(may|might|could|requires? validation|worth investigating)\b", re.IGNORECASE)
_DEFINITION_TOKEN = re.compile(r"\b(definition_version|definition|scope|cohort|population)\s*=\s*([^;|,]+)", re.I)


def _json_ids(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Product Evidence lineage must contain JSON arrays.") from exc
        if not isinstance(decoded, list):
            raise ValueError("Product Evidence lineage must contain JSON arrays.")
        return [str(item) for item in decoded]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    raise ValueError("Product Evidence lineage must contain JSON arrays.")


def _encode(values) -> str:
    return json.dumps(sorted(set(map(str, values))), ensure_ascii=False, separators=(",", ":"))


def _date_string(value):
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _product_evidence_id(evidence_type, statement, evidence_ids, pestel_ids, swot_ids, reference_date, hypothesis_ids=()):
    payload = {
        "product_evidence_type": evidence_type,
        "statement": statement,
        "source_evidence_ids": sorted(map(str, evidence_ids)),
        "source_pestel_ids": sorted(map(str, pestel_ids)),
        "source_swot_ids": sorted(map(str, swot_ids)),
        "reference_date": _date_string(reference_date),
        "source_hypothesis_ids": sorted(map(str, hypothesis_ids)),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _context_signatures(rows) -> dict[str, set[str]]:
    signatures: dict[str, set[str]] = {}
    for row in rows:
        for key, value in _DEFINITION_TOKEN.findall(str(row.get("definition_context") or "")):
            signatures.setdefault(key.casefold(), set()).add(value.strip().casefold())
    return signatures


def _population_signatures_by_series(rows) -> dict[tuple[str, str], set[str]]:
    """Keep population labels local to a metric/domain, not cross-domain."""
    signatures: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        domain = row.get("business_domain")
        metric_id = row.get("metric_id")
        if domain is None or pd.isna(domain) or metric_id is None or pd.isna(metric_id):
            continue
        for key, value in _DEFINITION_TOKEN.findall(str(row.get("definition_context") or "")):
            if key.casefold() == "population":
                signatures.setdefault((str(domain), str(metric_id)), set()).add(value.strip().casefold())
    return signatures


def _assert_compatible_period_and_definitions(rows) -> None:
    if not rows:
        raise ValueError("A cross-domain hypothesis requires source Evidence.")
    dates = {_date_string(row.get("reference_date")) for row in rows}
    if None in dates or len(dates) != 1:
        raise ValueError("Commerce and Fintech Evidence periods are incompatible.")
    for field in ("period_type", "period_label", "period_start", "period_end"):
        values = {
            _date_string(row.get(field)) if field in {"period_start", "period_end"} else str(row.get(field))
            for row in rows if row.get(field) is not None and not pd.isna(row.get(field))
        }
        if len(values) > 1:
            raise ValueError(f"Commerce and Fintech Evidence periods are incompatible: {field}.")
    context_signatures = _context_signatures(rows)
    conflicts = {
        key: values for key, values in context_signatures.items()
        if key != "population" and len(values) > 1
    }
    population_conflicts = {
        series: values for series, values in _population_signatures_by_series(rows).items()
        if len(values) > 1
    }
    if population_conflicts:
        conflicts["population"] = {
            f"{domain}/{metric_id}={value}"
            for (domain, metric_id), values in population_conflicts.items()
            for value in values
        }
    if conflicts:
        raise ValueError(f"Commerce and Fintech Evidence definitions are incompatible: {sorted(conflicts)}.")


def _lineage_for_row(row, evidence_by_id, known_ids):
    ids = sorted({str(row.evidence_id), *_json_ids(row.source_evidence_ids)})
    unknown = set(ids) - known_ids
    if unknown:
        raise ValueError(f"Unknown Evidence IDs: {sorted(unknown)}")
    return ids


def _metric_ids_for(ids, evidence_by_id):
    metrics = set()
    for evidence_id in ids:
        row = evidence_by_id[evidence_id]
        raw = row.source_metric_id
        if raw is not None and not pd.isna(raw):
            metrics.update(metric for metric in str(raw).split(";") if metric)
        elif row.metric_id is not None and not pd.isna(row.metric_id):
            metrics.add(str(row.metric_id))
    return sorted(metrics)


def _source_names(ids, evidence_by_id):
    return ";".join(sorted({str(evidence_by_id[evidence_id].source) for evidence_id in ids}))


def _select_metric_evidence(rows):
    by_metric: dict[str, list] = {}
    for row in rows:
        by_metric.setdefault(str(row.metric_id), []).append(row)
    selected = []
    for metric_id in sorted(by_metric):
        candidates = by_metric[metric_id]
        highest = max(_EVIDENCE_PRIORITY[str(row.evidence_type)] for row in candidates)
        preferred = [row for row in candidates if _EVIDENCE_PRIORITY[str(row.evidence_type)] == highest]
        if len(preferred) != 1:
            raise ValueError(f"Ambiguous Evidence for metric_id={metric_id!r} in a matching period.")
        selected.append(preferred[0])
    return selected


def _assert_strategy_record_compatible(strategy_row, evidence_ids, evidence_by_id):
    linked_rows = [evidence_by_id[evidence_id] for evidence_id in sorted(evidence_ids)]
    _assert_compatible_period_and_definitions([*linked_rows, strategy_row])


def _strategy_lineage(evidence_ids, reference_date, pestel_rows, swot_rows, evidence_by_id):
    selected_pestel = []
    for row in pestel_rows:
        ids = set(_json_ids(row.get("source_evidence_ids")))
        if ids and ids.issubset(evidence_ids):
            if _date_string(row.get("reference_date")) != _date_string(reference_date):
                raise ValueError("PESTEL period is incompatible with Product Evidence.")
            _assert_strategy_record_compatible(row, ids, evidence_by_id)
            selected_pestel.append(row)
    selected_swot = []
    for row in swot_rows:
        ids = set(_json_ids(row.get("source_evidence_ids")))
        if ids and ids.issubset(evidence_ids):
            if _date_string(row.get("reference_date")) != _date_string(reference_date):
                raise ValueError("SWOT period is incompatible with Product Evidence.")
            _assert_strategy_record_compatible(row, ids, evidence_by_id)
            selected_swot.append(row)
    pestel_ids = sorted({str(row["pestel_id"]) for row in selected_pestel})
    swot_ids = sorted({str(row["swot_id"]) for row in selected_swot})
    pestel_ids = sorted(set(pestel_ids) | {
        pestel_id for row in selected_swot for pestel_id in _json_ids(row.get("source_pestel_ids"))
    })
    return pestel_ids, swot_ids


def _record(
    *, evidence_type, statement, rationale, reference_date, period_start, period_end,
    period_type, entity, evidence_ids, interpretation_ids, pestel_ids, swot_ids,
    hypothesis_ids, metric_ids, source, definition_context,
):
    return {
        "product_evidence_id": _product_evidence_id(
            evidence_type, statement, evidence_ids, pestel_ids, swot_ids,
            reference_date, hypothesis_ids,
        ),
        "product_evidence_type": evidence_type,
        "discovery_theme": "ECOSYSTEM_ENGAGEMENT",
        "business_domain": "Ecosystem",
        "reference_date": reference_date,
        "period_start": period_start,
        "period_end": period_end,
        "period_type": period_type,
        "entity": entity,
        "statement": statement,
        "rationale": rationale,
        "source_evidence_ids": _encode(evidence_ids),
        "source_interpretation_ids": _encode(interpretation_ids),
        "source_pestel_ids": _encode(pestel_ids),
        "source_swot_ids": _encode(swot_ids),
        "source_hypothesis_ids": _encode(hypothesis_ids),
        "source_metric_ids": _encode(metric_ids),
        "source": source,
        "methodology_version": METHODOLOGY_VERSION,
        "definition_context": definition_context,
        "scope": "AGGREGATE",
    }


def _validate_language(frame: pd.DataFrame) -> None:
    for column in ("statement", "rationale"):
        for text in frame[column].astype(str):
            if _LANGUAGE_GUARD.search(text):
                raise ValueError(f"Product Evidence {column} contains causal, prescriptive, or unsupported user-need language.")
    hypotheses = frame.loc[frame.product_evidence_type.eq("HYPOTHESIS"), "statement"].astype(str)
    if any(not _UNCERTAINTY.search(text) for text in hypotheses):
        raise ValueError("HYPOTHESIS statements must use explicit uncertainty language.")
    questions = frame.loc[frame.product_evidence_type.eq("QUESTION_FOR_PRODUCT_DISCOVERY"), "statement"].astype(str)
    for text in questions:
        if not _QUESTION_START.search(text.strip()) or not text.strip().endswith("?"):
            raise ValueError("Discovery questions must be open-ended questions.")


def validate_product_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(PRODUCT_EVIDENCE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Product Evidence missing columns: {sorted(missing)}")
    result = frame[PRODUCT_EVIDENCE_COLUMNS].copy()
    invalid_types = set(result.product_evidence_type.dropna().astype(str)) - PRODUCT_EVIDENCE_TYPES
    if invalid_types:
        raise ValueError(f"Unsupported Product Evidence types: {sorted(invalid_types)}")
    invalid_themes = set(result.discovery_theme.dropna().astype(str)) - DISCOVERY_THEMES
    if invalid_themes:
        raise ValueError(f"Unsupported Product discovery themes: {sorted(invalid_themes)}")
    required = [
        "product_evidence_id", "product_evidence_type", "discovery_theme", "business_domain",
        "statement", "rationale", "source_evidence_ids", "source_interpretation_ids",
        "source_pestel_ids", "source_swot_ids", "source_hypothesis_ids", "source_metric_ids",
        "source", "methodology_version", "definition_context", "scope",
    ]
    if result[required].isna().any().any():
        raise ValueError("Product Evidence required fields cannot be null.")
    if result.product_evidence_id.astype(str).str.strip().eq("").any() or result.product_evidence_id.duplicated(keep=False).any():
        raise ValueError("Product Evidence IDs must be non-empty and unique.")
    hypothesis_rows = result.loc[result.product_evidence_type.eq("HYPOTHESIS")]
    known_hypotheses = set(hypothesis_rows.product_evidence_id.astype(str))
    for _, row in result.iterrows():
        evidence_ids = _json_ids(row.source_evidence_ids)
        interpretation_ids = _json_ids(row.source_interpretation_ids)
        hypothesis_ids = _json_ids(row.source_hypothesis_ids)
        if not evidence_ids:
            raise ValueError("Product Evidence must preserve non-empty Evidence lineage.")
        if not set(interpretation_ids).issubset(set(evidence_ids)):
            raise ValueError("Interpretation IDs must be included in source Evidence lineage.")
        if row.product_evidence_type == "HYPOTHESIS" and hypothesis_ids:
            raise ValueError("HYPOTHESIS rows cannot reference source hypotheses.")
        if row.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY":
            if not hypothesis_ids:
                raise ValueError("Discovery questions must reference at least one hypothesis.")
            unknown_hypotheses = set(hypothesis_ids) - known_hypotheses
            if unknown_hypotheses:
                raise ValueError(f"Unknown hypothesis IDs: {sorted(unknown_hypotheses)}")
    _validate_language(result)
    for column in ("reference_date", "period_start", "period_end"):
        result[column] = pd.to_datetime(result[column], errors="raise").dt.date
    by_id = {str(row.product_evidence_id): row for _, row in result.iterrows()}
    for _, row in result.loc[result.product_evidence_type.eq("QUESTION_FOR_PRODUCT_DISCOVERY")].iterrows():
        for hypothesis_id in _json_ids(row.source_hypothesis_ids):
            hypothesis = by_id[hypothesis_id]
            for column in (
                "source_evidence_ids", "source_interpretation_ids", "source_pestel_ids",
                "source_swot_ids", "source_metric_ids",
            ):
                if _json_ids(row[column]) != _json_ids(hypothesis[column]):
                    raise ValueError("Discovery question lineage must match its hypothesis.")
            if _date_string(row.reference_date) != _date_string(hypothesis.reference_date):
                raise ValueError("Discovery question period must match its hypothesis.")
    return result.sort_values(
        ["reference_date", "product_evidence_type", "discovery_theme", "product_evidence_id"],
        na_position="last", kind="mergesort",
    ).reset_index(drop=True)


def _validate_strategy_inputs(evidence, pestel, swot):
    pestel_rows = []
    swot_rows = []
    if pestel is not None:
        p = validate_pestel(pestel)
        validate_pestel_lineage(p, evidence)
        pestel_rows = p.to_dict("records")
    if swot is not None:
        s = validate_swot(swot)
        validate_swot_lineage(s, evidence, pestel)
        swot_rows = s.to_dict("records")
    return pestel_rows, swot_rows


def validate_product_evidence_lineage(product_evidence, evidence_registry, pestel=None, swot=None) -> None:
    evidence = normalize_evidence(evidence_registry)
    product = validate_product_evidence(product_evidence)
    evidence_by_id = {str(row.evidence_id): row for _, row in evidence.iterrows()}
    known_evidence = set(evidence_by_id)
    evidence_types = dict(zip(evidence.evidence_id.astype(str), evidence.evidence_type.astype(str)))
    pestel_by_id = {}
    swot_by_id = {}
    if pestel is not None:
        p = validate_pestel(pestel)
        validate_pestel_lineage(p, evidence)
        pestel_by_id = {str(row.pestel_id): row for _, row in p.iterrows()}
    if swot is not None:
        s = validate_swot(swot)
        validate_swot_lineage(s, evidence, pestel)
        swot_by_id = {str(row.swot_id): row for _, row in s.iterrows()}
    for _, row in product.iterrows():
        evidence_ids = _json_ids(row.source_evidence_ids)
        unknown_evidence = set(evidence_ids) - known_evidence
        if unknown_evidence:
            raise ValueError(f"Unknown Evidence IDs: {sorted(unknown_evidence)}")
        interpretations = _json_ids(row.source_interpretation_ids)
        wrong_types = [eid for eid in interpretations if evidence_types.get(eid) != "INTERPRETATION"]
        if wrong_types:
            raise ValueError(f"source_interpretation_ids must reference INTERPRETATION rows: {sorted(wrong_types)}")
        if not set(interpretations).issubset(set(evidence_ids)):
            raise ValueError("Interpretation lineage must be a subset of source Evidence lineage.")
        expected_metrics = _metric_ids_for(evidence_ids, evidence_by_id)
        if expected_metrics != _json_ids(row.source_metric_ids):
            raise ValueError("Product source_metric_ids do not match the Evidence Registry.")
        _assert_compatible_period_and_definitions([evidence_by_id[eid] for eid in evidence_ids])
        pids = _json_ids(row.source_pestel_ids)
        if pids and pestel is None:
            raise ValueError("PESTEL dataset is required to validate Product Evidence lineage.")
        unknown_pestel = set(pids) - set(pestel_by_id)
        if unknown_pestel:
            raise ValueError(f"Unknown PESTEL IDs: {sorted(unknown_pestel)}")
        for pestel_id in pids:
            strategy_ids = set(_json_ids(pestel_by_id[pestel_id].source_evidence_ids))
            if not strategy_ids or not strategy_ids.issubset(set(evidence_ids)):
                raise ValueError("PESTEL Evidence lineage is incompatible with Product Evidence.")
            _assert_strategy_record_compatible(pestel_by_id[pestel_id], strategy_ids, evidence_by_id)
            if _date_string(pestel_by_id[pestel_id].reference_date) != _date_string(row.reference_date):
                raise ValueError("PESTEL period is incompatible with Product Evidence.")
        swot_ids = _json_ids(row.source_swot_ids)
        if swot_ids and swot is None:
            raise ValueError("SWOT dataset is required to validate Product Evidence lineage.")
        unknown_swot = set(swot_ids) - set(swot_by_id)
        if unknown_swot:
            raise ValueError(f"Unknown SWOT IDs: {sorted(unknown_swot)}")
        for swot_id in swot_ids:
            strategy_ids = set(_json_ids(swot_by_id[swot_id].source_evidence_ids))
            if not strategy_ids or not strategy_ids.issubset(set(evidence_ids)):
                raise ValueError("SWOT Evidence lineage is incompatible with Product Evidence.")
            _assert_strategy_record_compatible(swot_by_id[swot_id], strategy_ids, evidence_by_id)
            if _date_string(swot_by_id[swot_id].reference_date) != _date_string(row.reference_date):
                raise ValueError("SWOT period is incompatible with Product Evidence.")
            nested_pestel = set(_json_ids(swot_by_id[swot_id].source_pestel_ids))
            if not nested_pestel.issubset(set(pids)):
                raise ValueError("Product Evidence must preserve the PESTEL lineage of linked SWOT.")
        if row.product_evidence_type == "QUESTION_FOR_PRODUCT_DISCOVERY":
            hypotheses = _json_ids(row.source_hypothesis_ids)
            missing_hypotheses = set(hypotheses) - set(product.product_evidence_id.astype(str))
            if missing_hypotheses:
                raise ValueError(f"Unknown hypothesis IDs: {sorted(missing_hypotheses)}")


def build_product_evidence(evidence_registry, pestel=None, swot=None) -> pd.DataFrame:
    """Create only compatible Commerce/Fintech engagement hypotheses and their questions."""
    evidence = normalize_evidence(evidence_registry)
    evidence_by_id = {str(row.evidence_id): row for _, row in evidence.iterrows()}
    known_ids = set(evidence_by_id)
    pestel_rows, swot_rows = _validate_strategy_inputs(evidence, pestel, swot)
    eligible = evidence.loc[
        evidence.metric_id.isin(_COMMERCE_METRICS | _FINTECH_METRICS)
        & evidence.reference_date.notna()
        & evidence.evidence_type.isin(EVIDENCE_TYPES)
    ]
    eligible = eligible.loc[
        ((eligible.business_domain == "Commerce") & eligible.metric_id.isin(_COMMERCE_METRICS))
        | ((eligible.business_domain == "Fintech") & eligible.metric_id.isin(_FINTECH_METRICS))
    ]
    grouped: dict[str, list] = {}
    for _, row in eligible.iterrows():
        grouped.setdefault(_date_string(row.reference_date), []).append(row)
    output = []
    for _, rows in sorted(grouped.items()):
        selected = _select_metric_evidence(rows)
        commerce = [row for row in selected if row.business_domain == "Commerce"]
        fintech = [row for row in selected if row.business_domain == "Fintech"]
        if not commerce or not fintech:
            continue
        _assert_compatible_period_and_definitions(selected)
        chosen_ids = set()
        for row in selected:
            chosen_ids.update(_lineage_for_row(row, evidence_by_id, known_ids))
        chosen_ids = sorted(chosen_ids)
        chosen_rows = [evidence_by_id[evidence_id] for evidence_id in chosen_ids]
        _assert_compatible_period_and_definitions(chosen_rows)
        reference_date = selected[0].reference_date
        pestel_ids, swot_ids = _strategy_lineage(chosen_ids, reference_date, pestel_rows, swot_rows, evidence_by_id)
        s_by_id = {str(row["swot_id"]): row for row in swot_rows}
        for swot_id in swot_ids:
            swot_pestel_ids = _json_ids(s_by_id[swot_id].get("source_pestel_ids"))
            if not set(swot_pestel_ids).issubset(set(pestel_ids)):
                raise ValueError("Linked SWOT PESTEL lineage is not compatible with Product Evidence.")
        interpretation_ids = sorted(
            evidence_id for evidence_id in chosen_ids
            if evidence_by_id[evidence_id].evidence_type == "INTERPRETATION"
        )
        metric_ids = _metric_ids_for(chosen_ids, evidence_by_id)
        period_starts = [row.period_start for row in chosen_rows if pd.notna(row.period_start)]
        period_ends = [row.period_end for row in chosen_rows if pd.notna(row.period_end)]
        period_types = {str(row.period_type) for row in chosen_rows if pd.notna(row.period_type)}
        entities = {str(row.entity) for row in chosen_rows if pd.notna(row.entity)}
        definition_context = ";".join(sorted({str(row.definition_context) for row in chosen_rows}))
        definition_context += ";aggregate_metrics_only;no_user_level_overlap_inference"
        hypothesis = _record(
            evidence_type="HYPOTHESIS", statement=_HYPOTHESIS_STATEMENT,
            rationale=_HYPOTHESIS_RATIONALE, reference_date=reference_date,
            period_start=min(period_starts) if period_starts else None,
            period_end=max(period_ends) if period_ends else None,
            period_type=next(iter(period_types)) if period_types else None,
            entity=next(iter(entities)) if len(entities) == 1 else None,
            evidence_ids=chosen_ids, interpretation_ids=interpretation_ids,
            pestel_ids=pestel_ids, swot_ids=swot_ids, hypothesis_ids=[],
            metric_ids=metric_ids, source=_source_names(chosen_ids, evidence_by_id),
            definition_context=definition_context,
        )
        output.append(hypothesis)
        question = _record(
            evidence_type="QUESTION_FOR_PRODUCT_DISCOVERY", statement=_QUESTION_STATEMENT,
            rationale=_QUESTION_RATIONALE, reference_date=reference_date,
            period_start=hypothesis["period_start"], period_end=hypothesis["period_end"],
            period_type=hypothesis["period_type"], entity=hypothesis["entity"],
            evidence_ids=chosen_ids, interpretation_ids=interpretation_ids,
            pestel_ids=pestel_ids, swot_ids=swot_ids,
            hypothesis_ids=[hypothesis["product_evidence_id"]], metric_ids=metric_ids,
            source=_source_names(chosen_ids, evidence_by_id), definition_context=definition_context,
        )
        output.append(question)
    result = pd.DataFrame(output, columns=PRODUCT_EVIDENCE_COLUMNS)
    if result.empty:
        return result
    result = validate_product_evidence(result)
    validate_product_evidence_lineage(result, evidence, pestel, swot)
    return result
