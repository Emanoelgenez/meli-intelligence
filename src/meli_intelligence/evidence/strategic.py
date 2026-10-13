"""Pure strategic preparation with separately auditable calculation lineage.

Common source_evidence_ids are contemporary support for the unchanged strategy
builders. Calculation edges retain both native-period operands, never redating
prior facts to satisfy those builders. No acquisition or persistence occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

import pandas as pd
import pyarrow as pa

from meli_intelligence.analytics import financial as fin, operational as op
from meli_intelligence.analytics.macro import build_macro_analytics
from meli_intelligence.analytics.macro_evidence import build_macro_observations
from meli_intelligence.evidence.adapters import (
    _id, adapt_financial_evidence, adapt_macro_evidence, adapt_operational_evidence,
)
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence
from meli_intelligence.storage.macro import validate_macro_indicators

OPERATIONAL_METRICS = {
    "gmv": ("Commerce", "USD"), "unique_active_buyers": ("Commerce", "users"),
    "fintech_mau": ("Fintech", "users"), "tpv": ("Fintech", "USD"),
}
LINEAGE_SCHEMA = pa.schema([
    pa.field("observation_id", pa.string(), nullable=False),
    pa.field("source_evidence_id", pa.string(), nullable=False),
    pa.field("role", pa.string(), nullable=False),
    pa.field("operation", pa.string(), nullable=False),
    pa.field("source_series_id", pa.string()),
], metadata={b"schema_version": b"1"})
OMISSION_COLUMNS = ["source_evidence_id", "metric_id", "period_start", "period_end", "accession_number", "reason"]


@dataclass
class StrategicEvidence:
    registry: pd.DataFrame
    lineage: pd.DataFrame
    omissions: pd.DataFrame


def _empty():
    return pd.DataFrame(columns=EVIDENCE_COLUMNS)


def _day(value):
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date()


def _shape(value):
    value = _day(value)
    return None if value is None else (value.month, value.day)


def _definition_signature(context):
    keys = {"definition_version", "definition", "scope", "cohort", "population"}
    return sorted(tuple(part.split("=", 1)) for part in str(context).split(";")
                  if "=" in part and part.split("=", 1)[0] in keys)


def _finish(frames, edges, omissions):
    registry = normalize_evidence(pd.concat(frames, ignore_index=True)) if frames else _empty()
    lineage = pd.DataFrame(edges, columns=LINEAGE_SCHEMA.names).sort_values(
        ["observation_id", "role"], kind="stable").reset_index(drop=True)
    result = StrategicEvidence(registry, lineage, pd.DataFrame(omissions, columns=OMISSION_COLUMNS))
    validate_derivation_lineage(result.registry, result.lineage)
    return result


def _edge(child, parent, role, operation, series=None):
    return dict(observation_id=child, source_evidence_id=parent, role=role,
                operation=operation, source_series_id=series)


def _validate_company(facts, operational):
    required = set(fin.PERIOD_KEY) | {"metric_id", "unit", "value", "entity_cik", "entity_name", "source", "accession_number"}
    if operational:
        required.add("definition_version")
    missing = required - set(facts.columns)
    if missing:
        raise ValueError(f"Company evidence missing columns: {sorted(missing)}")
    f = facts.copy()
    for column in ("period_start", "period_end"):
        f[column] = pd.to_datetime(f[column], errors="raise").dt.date
    if f[list(required - {"period_start"})].isna().any().any():
        raise ValueError("Company evidence required fields cannot be null.")
    for column in ("entity_cik", "entity_name", "source", "accession_number", "unit", "period_type", "period_label"):
        if f[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Company evidence {column} cannot be empty.")
    if not pd.to_numeric(f.value, errors="raise").map(math.isfinite).all():
        raise ValueError("Company values must be finite.")
    for row in f.to_dict("records"):
        if int(row["reference_year"]) != row["period_end"].year:
            raise ValueError("Company reference_year disagrees with period_end.")
        if row["period_type"] == "INSTANT":
            if _day(row["period_start"]) is not None:
                raise ValueError("Instant facts cannot have a period_start.")
        elif _day(row["period_start"]) is None or row["period_start"] > row["period_end"]:
            raise ValueError("Invalid company period boundaries.")
    # This bridge accepts the consolidated Silver contract, not segment/geo facts.
    for column in ("scope", "segment", "geography"):
        if column in f and f[column].notna().any():
            raise ValueError(f"Unsupported company scope column: {column}.")
    return f


def _company(facts, operational):
    if facts is None or facts.empty:
        return _finish([], [], [dict(source_evidence_id=None, metric_id=None, reason="company input absent or empty")])
    f = _validate_company(facts, operational)
    metrics = OPERATIONAL_METRICS if operational else {m: ("Financial", "USD") for m in fin.YOY_SOURCE_METRICS}
    raw, sources, omissions, edges, observations = [], [], [], [], []
    for row in f.to_dict("records"):
        if operational and row["metric_id"] not in metrics:
            omissions.append(dict(source_evidence_id=None, metric_id=row["metric_id"], period_start=row["period_start"], period_end=row["period_end"], accession_number=row["accession_number"], reason="outside operational bridge metric scope"))
            continue
        supplied = dict(row)
        if row["metric_id"] in metrics:
            domain, unit = metrics[row["metric_id"]]
            if row["unit"] != unit:
                raise ValueError("Company unit is incompatible with the metric.")
            if "business_domain" in row and pd.notna(row["business_domain"]) and row["business_domain"] != domain:
                raise ValueError("Company business domain is incompatible with the metric.")
            supplied["business_domain"] = domain
        if operational:
            version = str(row["definition_version"])
            if not version.strip():
                raise ValueError("Operational definition_version cannot be empty.")
            family = op._comparison_family(row["metric_id"], version)
            supplied.update(evidence_type="FACT", definition_context=f"definition_version={family};reported_definition={version}",
                            claim=f"Reported {row['metric_id']} was {float(row['value']):.15g} {row['unit']} at {row['period_end']}.")
        evidence = adapt_financial_evidence(pd.DataFrame([supplied])).iloc[0].to_dict()
        if operational and (pd.isna(row.get("evidence_id")) or not str(row.get("evidence_id", "")).strip()):
            evidence["evidence_id"] = _id({"namespace": "operational-kpi-v1", "fact": evidence["evidence_id"], "definition": version})
        raw.append(evidence)
        sources.append(dict(row, _evidence=evidence))
    raw_frame = normalize_evidence(pd.DataFrame(raw, columns=EVIDENCE_COLUMNS))
    used = set()
    for metric in metrics:
        selected = [r for r in sources if r["metric_id"] == metric]
        if not selected:
            continue
        for entity in sorted({r["entity_cik"] for r in selected}):
            group = [r for r in selected if r["entity_cik"] == entity]
            calculator = op.calculate_yoy_growth if operational else fin.calculate_yoy_growth
            analytics = calculator(pd.DataFrame(group), metric)
            for derived in analytics.to_dict("records"):
                current = [r for r in group if all(_day(r[k]) == _day(derived[k]) for k in ("period_start", "period_end"))
                           and r["period_type"] == derived["period_type"] and r["period_label"] == derived["period_label"]]
                if len(current) != 1:
                    raise ValueError("Ambiguous current company evidence.")
                current = current[0]
                previous = [r for r in group if r["reference_year"] == current["reference_year"] - 1
                            and r["period_type"] == current["period_type"] and r["period_label"] == current["period_label"]
                            and _shape(r["period_start"]) == _shape(current["period_start"])
                            and _shape(r["period_end"]) == _shape(current["period_end"])
                            and (not operational or op._comparison_family(metric, r["definition_version"]) == op._comparison_family(metric, current["definition_version"]))]
                if len(previous) != 1:
                    raise ValueError("Missing or ambiguous prior-year evidence.")
                previous = previous[0]
                parents = [current["_evidence"], previous["_evidence"]]
                context = parents[0]["definition_context"] + ";derivation_version=1;formula=" + derived["formula"]
                record = dict(derived, entity_name=current["entity_name"], entity_cik=entity,
                              business_domain=metrics[metric][0], source=current["source"],
                              definition_context=context, source_evidence_ids=[parents[0]["evidence_id"]])
                record["evidence_id"] = _id({"namespace": "company-yoy-v1", "current": parents[0]["evidence_id"],
                                             "previous": parents[1]["evidence_id"], "metric": derived["metric_id"], "value": float(derived["value"])})
                observation = adapt_financial_evidence(pd.DataFrame([record])).iloc[0].to_dict()
                observations.append(observation)
                for role, parent in zip(("current", "previous"), parents):
                    edges.append(_edge(observation["evidence_id"], parent["evidence_id"], role, "yoy"))
                used.add(parents[0]["evidence_id"])
    for row in raw:
        if row["evidence_id"] not in used:
            reason = "outside financial YoY metric scope" if row["metric_id"] not in metrics else "no comparable positive prior-year baseline or eligible period"
            omissions.append(dict(source_evidence_id=row["evidence_id"], metric_id=row["metric_id"], reason=reason))
    return _finish([raw_frame, pd.DataFrame(observations, columns=EVIDENCE_COLUMNS)], edges, omissions)


def adapt_financial_strategic_evidence(facts):
    """Preserve financial facts and derive verified existing financial YoY metrics."""
    return _company(facts, False)


def adapt_operational_strategic_evidence(facts):
    """Bridge the four approved consolidated operational KPI families and their YoY."""
    return _company(facts, True)


def adapt_macro_strategic_evidence(facts):
    """Build numeric macro observations and calculation edges, using local inputs only."""
    if facts is None or facts.empty:
        return _finish([], [], [dict(source_evidence_id=None, metric_id=None, reason="macro input absent or empty")])
    validate_macro_indicators(facts)
    f = facts.copy()
    f["reference_date"] = pd.to_datetime(f.reference_date).dt.date
    for _, series in f.groupby("metric_id"):
        if any(series[c].nunique() != 1 for c in ("source_series_id", "source", "unit", "frequency")):
            raise ValueError("Macro series identity, unit or frequency changes within a metric.")
    analytics = build_macro_analytics(f)
    observations = build_macro_observations(f, analytics)
    common = adapt_macro_evidence(observations)
    by_key = {(r.metric_id, r.reference_date): r.to_dict() for _, r in common.iterrows()}
    raw = {(r.metric_id, r.reference_date): r.to_dict() for _, r in f.iterrows()}
    for key, source in raw.items():
        by_key[key]["evidence_id"] = _id({"namespace": "macro-source-v1", "observation": by_key[key]["evidence_id"],
                                         "series": source["source_series_id"], "url": source["source_url"]})
    edges = []
    for row in analytics.to_dict("records"):
        key = (row["metric_id"], row["reference_date"])
        child = by_key[key]
        source_metric = row["source_metric_id"]
        current_date = _day(row["source_reference_date"]) or row["reference_date"]
        previous_date = _day(row["previous_reference_date"])
        operation = "snapshot" if row["analytics_kind"] == "month_end_snapshot" else "percent_change" if row["unit"] == "percent" else "difference"
        parents = []
        for role, ref in (("current", current_date), ("previous", previous_date)):
            if ref is None:
                continue
            if row["metric_id"] == "usd_brl_monthly_change_pct":
                matches = [r for (m, d), r in raw.items() if m == source_metric and (d.year, d.month) == (ref.year, ref.month)]
                if not matches:
                    raise ValueError("Missing FX source observation.")
                ref = max(r["reference_date"] for r in matches)
            parent = by_key.get((source_metric, ref))
            if parent is None:
                raise ValueError("Missing macro calculation source.")
            parents.append((role, parent))
            edges.append(_edge(child["evidence_id"], parent["evidence_id"], role, operation, raw[(source_metric, ref)]["source_series_id"]))
        old_id = child["evidence_id"]
        child["evidence_id"] = _id({"namespace": "macro-calculation-v1", "observation": old_id,
                                     "operands": [(role, p["evidence_id"]) for role, p in parents]})
        for edge in edges:
            if edge["observation_id"] == old_id:
                edge["observation_id"] = child["evidence_id"]
        child["definition_context"] += ";derivation_version=1"
        child["source_evidence_ids"] = json.dumps([p["evidence_id"] for role, p in parents if role == "current" and p["reference_date"] == child["reference_date"]])
    # Preserve official series and source URL without changing the common schema.
    for key, row in by_key.items():
        if key in raw:
            row["source_url"] = raw[key]["source_url"]
            row["definition_context"] += ";source_series_id=" + str(raw[key]["source_series_id"])
    return _finish([pd.DataFrame(by_key.values(), columns=EVIDENCE_COLUMNS)], edges, [])


def build_strategic_evidence(*, financial=None, operational_kpis=None, operational=None, macro=None):
    """Return registry, calculation lineage and omissions, without strategy or I/O."""
    bundles = [adapt_financial_strategic_evidence(financial),
               adapt_operational_strategic_evidence(operational_kpis), adapt_macro_strategic_evidence(macro)]
    frames = [b.registry for b in bundles]
    if operational is not None and not operational.empty:
        frames.append(adapt_operational_evidence(operational))
    return _finish(frames, [r for b in bundles for r in b.lineage.to_dict("records")],
                   [r for b in bundles for r in b.omissions.to_dict("records")])


def validate_derivation_lineage(registry, lineage):
    """Reject missing/duplicate operands, invalid periods/scopes and unverified values."""
    registry = normalize_evidence(registry)
    if set(LINEAGE_SCHEMA.names) - set(lineage.columns):
        raise ValueError("Calculation lineage columns missing.")
    pa.Table.from_pandas(lineage, schema=LINEAGE_SCHEMA, preserve_index=False, safe=True).validate(full=True)
    if lineage.duplicated(["observation_id", "role"]).any():
        raise ValueError("Duplicate calculation operand role.")
    by_id = registry.set_index("evidence_id").to_dict("index")
    expected = set(registry.loc[registry.definition_context.str.contains("derivation_version=1", regex=False), "evidence_id"])
    if set(lineage.observation_id) != expected:
        raise ValueError("Calculation lineage does not cover derived observations.")
    for child_id, group in lineage.groupby("observation_id"):
        if child_id not in by_id or not set(group.source_evidence_id).issubset(by_id):
            raise ValueError("Unknown calculation evidence ID.")
        child = by_id[child_id]
        operations = set(group.operation)
        if len(operations) != 1 or not operations.issubset({"yoy", "percent_change", "difference", "snapshot"}):
            raise ValueError("Invalid calculation operation.")
        operation = next(iter(operations))
        roles = set(group.role)
        if roles != ({"current"} if operation == "snapshot" else {"current", "previous"}):
            raise ValueError("Missing calculation operand.")
        parents = {r.role: by_id[r.source_evidence_id] for r in group.itertuples()}
        current = parents["current"]
        if child["evidence_type"] != "OBSERVATION" or child["business_domain"] != current["business_domain"] or child["entity"] != current["entity"] or child["source"] != current["source"]:
            raise ValueError("Invalid calculation evidence type/domain.")
        if any(p["metric_id"] != child["source_metric_id"] or p["business_domain"] != child["business_domain"] or p["entity"] != current["entity"] for p in parents.values()):
            raise ValueError("Incompatible calculation metric, domain or entity.")
        if not all(p["value"] is not None and not pd.isna(p["value"]) and math.isfinite(float(p["value"])) for p in [child, *parents.values()]):
            raise ValueError("Missing or nonfinite calculation value.")
        previous = parents.get("previous")
        if previous:
            if previous["reference_date"] >= current["reference_date"] or previous["unit"] != current["unit"]:
                raise ValueError("Incompatible calculation periods/units.")
        if operation == "yoy":
            if child["metric_id"] != current["metric_id"] + "_yoy_growth" or child["unit"] != "percent" or previous["value"] <= 0:
                raise ValueError("Invalid YoY definition or baseline.")
            if current["reference_date"].year != previous["reference_date"].year + 1 or any(
                _shape(current[k]) != _shape(previous[k]) for k in ("period_start", "period_end")
            ) or any(current[k] != previous[k] for k in ("period_type", "period_label")):
                raise ValueError("Incompatible YoY periods.")
            if _day(current["period_start"]) is not None and current["period_start"].year != previous["period_start"].year + 1:
                raise ValueError("Incompatible YoY duration years.")
            if _definition_signature(current["definition_context"]) != _definition_signature(previous["definition_context"]):
                raise ValueError("Incompatible YoY definitions.")
            if any(_day(child[k]) != _day(current[k]) for k in ("reference_date", "period_start", "period_end")) or any(child[k] != current[k] for k in ("period_type", "period_label")):
                raise ValueError("Derived period differs from current source.")
        else:
            _validate_macro_periods(child, parents, group, registry, operation)
        expected_support = sorted(group.loc[group.role.eq("current"), "source_evidence_id"]) if _day(child["reference_date"]) == _day(current["reference_date"]) else []
        if json.loads(child["source_evidence_ids"]) != expected_support:
            raise ValueError("Contemporary support does not match calculation lineage.")
        if operation in {"yoy", "percent_change"}:
            if previous["value"] == 0 or child["unit"] != "percent":
                raise ValueError("Invalid percentage calculation.")
            value = (current["value"] / previous["value"] - 1) * 100
        elif operation == "difference":
            value = current["value"] - previous["value"]
        else:
            value = current["value"]
        if not math.isclose(child["value"], value, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Calculation value does not match its sources.")


_MACRO_RULES = {
    "selic_target_change_pp": ("selic_target_annual", "difference", "previous"),
    "ipca_12m_change_pp": ("ipca_12m_change", "difference", "month"),
    "usd_brl_month_end": ("usd_brl_sell_rate", "snapshot", "fx"),
    "usd_brl_monthly_change_pct": ("usd_brl_sell_rate", "percent_change", "fx_month"),
    "household_free_credit_balance_yoy_growth": ("household_free_credit_balance", "percent_change", "year"),
    "household_free_credit_npl_90d_yoy_change_pp": ("household_free_credit_npl_90d_rate", "difference", "year"),
    "ibc_br_activity_mom_change_pct": ("ibc_br_activity_sa_index", "percent_change", "month"),
    "unemployment_rate_change_pp": ("unemployment_rate_rolling_3m", "difference", "previous"),
    "pix_transactions_count_yoy_growth": ("pix_transactions_count_monthly", "percent_change", "year"),
    "pix_transactions_value_yoy_growth": ("pix_transactions_value_monthly", "percent_change", "year"),
}


def _validate_macro_periods(child, parents, edges, registry, operation):
    rule = _MACRO_RULES.get(child["metric_id"])
    if rule is None or rule[:2] != (child["source_metric_id"], operation) or child["business_domain"] != "Macro":
        raise ValueError("Unapproved macro calculation contract.")
    current, previous = parents["current"], parents.get("previous")
    temporal = rule[2]
    ref = child["reference_date"]
    if current["reference_date"] > ref:
        raise ValueError("Macro source is later than its observation.")
    series = registry.loc[registry.metric_id.eq(current["metric_id"]) & registry.business_domain.eq("Macro")]
    if edges.source_series_id.isna().any() or edges.source_series_id.nunique() != 1:
        raise ValueError("Incompatible macro series lineage.")
    for edge in edges.itertuples():
        parent = parents[edge.role]
        signature = "source_series_id=" + str(edge.source_series_id)
        if signature not in str(parent["definition_context"]).split(";"):
            raise ValueError("Macro source series lineage mismatch.")
    if previous and any(previous[k] != current[k] for k in ("source", "frequency")):
        raise ValueError("Incompatible macro source series.")
    expected_unit = "percentage_points" if operation == "difference" else current["unit"] if operation == "snapshot" else "percent"
    expected_frequency = "monthly" if temporal.startswith("fx") else current["frequency"]
    if child["unit"] != expected_unit or child["frequency"] != expected_frequency:
        raise ValueError("Incompatible macro output unit/frequency.")
    if temporal.startswith("fx"):
        if ref != (pd.Timestamp(ref) + pd.offsets.MonthEnd(0)).date():
            raise ValueError("FX observations require calendar month-end.")
        for role, parent in parents.items():
            month = pd.Timestamp(ref).to_period("M") - (1 if role == "previous" else 0)
            candidates = series.loc[pd.to_datetime(series.reference_date).dt.to_period("M").eq(month)]
            if candidates.empty or parent["reference_date"] != candidates.reference_date.max():
                raise ValueError("FX lineage must use the last available quote in its month.")
    elif current["reference_date"] != ref:
        raise ValueError("Macro current source period mismatch.")
    elif temporal in {"month", "year"}:
        shift = 12 if temporal == "year" else 1
        if pd.Timestamp(previous["reference_date"]).to_period("M") != pd.Timestamp(ref).to_period("M") - shift:
            raise ValueError("Incompatible macro calendar periods.")
    elif temporal == "previous":
        prior = series.loc[series.reference_date.lt(ref)]
        if prior.empty or previous["reference_date"] != prior.reference_date.max():
            raise ValueError("Macro lineage must use the previous published observation.")
