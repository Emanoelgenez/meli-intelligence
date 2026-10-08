"""Normalize selected SEC Company Facts into canonical financial facts."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from typing import Any

from meli_intelligence.sources.sec.client import company_facts_url, normalize_cik


SEC_CONCEPT_MAP = {
    "net_revenues_financial_income": {
        "taxonomy": "us-gaap",
        "concept": "Revenues",
    },
    "gross_profit": {
        "taxonomy": "us-gaap",
        "concept": "GrossProfit",
    },
    "operating_income": {
        "taxonomy": "us-gaap",
        "concept": "OperatingIncomeLoss",
    },
    "net_income": {
        "taxonomy": "us-gaap",
        "concept": "NetIncomeLoss",
    },
    "cash_and_equivalents": {
        "taxonomy": "us-gaap",
        "concept": "CashAndCashEquivalentsAtCarryingValue",
    },
    "total_assets": {
        "taxonomy": "us-gaap",
        "concept": "Assets",
    },
    "total_liabilities": {
        "taxonomy": "us-gaap",
        "concept": "Liabilities",
    },
    "stockholders_equity": {
        "taxonomy": "us-gaap",
        "concept": "StockholdersEquity",
    },
    "operating_cash_flow": {
        "taxonomy": "us-gaap",
        "concept": "NetCashProvidedByUsedInOperatingActivities",
    },
    "capex_productive_assets": {
        "taxonomy": "us-gaap",
        "concept": "PaymentsToAcquireProductiveAssets",
    },
    "capex_ppe_legacy": {
        "taxonomy": "us-gaap",
        "concept": "PaymentsToAcquirePropertyPlantAndEquipment",
    },
}


ALLOWED_FORMS = {"10-K", "10-Q"}
SEC_SHARES_OUTSTANDING_TAXONOMY = "dei"
SEC_SHARES_OUTSTANDING_CONCEPT = "EntityCommonStockSharesOutstanding"
SEC_SHARES_OUTSTANDING_METRIC_ID = "shares_outstanding"
MELI_CIK = "0001099590"


def normalize_shares_outstanding(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract only explicit SEC DEI shares outstanding from Company Facts.

    Share count is an instant fact with its own ``shares`` unit; it is kept
    separate from the USD financial-facts Silver schema.
    """
    if normalize_cik(payload.get("cik", "")) != MELI_CIK:
        raise ValueError("Shares outstanding payload is not MercadoLibre Company Facts.")
    entity_name = payload.get("entityName")
    if not isinstance(entity_name, str) or not entity_name.strip():
        raise ValueError("Shares outstanding payload is missing entityName.")

    concept = (
        payload.get("facts", {})
        .get(SEC_SHARES_OUTSTANDING_TAXONOMY, {})
        .get(SEC_SHARES_OUTSTANDING_CONCEPT)
    )
    if not isinstance(concept, dict):
        return []

    rows: list[dict[str, Any]] = []
    for unit, observations in concept.get("units", {}).items():
        if unit.casefold() != "shares":
            continue
        for observation in observations:
            if observation.get("form") not in ALLOWED_FORMS:
                continue
            if observation.get("start") is not None:
                continue
            end = observation.get("end")
            filed = observation.get("filed")
            accession = observation.get("accn")
            value = observation.get("val")
            try:
                reference_date = date.fromisoformat(str(end))
                filed_at = date.fromisoformat(str(filed))
                numeric_value = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(numeric_value) or numeric_value <= 0:
                continue
            if not isinstance(accession, str) or not accession.strip():
                continue
            cik = normalize_cik(payload["cik"])
            rows.append({
                "entity": entity_name.strip(),
                "metric_id": SEC_SHARES_OUTSTANDING_METRIC_ID,
                "source_metric_id": f"{SEC_SHARES_OUTSTANDING_TAXONOMY}:{SEC_SHARES_OUTSTANDING_CONCEPT}",
                "taxonomy": SEC_SHARES_OUTSTANDING_TAXONOMY,
                "concept": SEC_SHARES_OUTSTANDING_CONCEPT,
                "reference_date": reference_date,
                "value": numeric_value,
                "unit": "shares",
                "filed_at": filed_at,
                "accession_number": accession.strip(),
                "form": observation["form"],
                "source": "SEC EDGAR Company Facts API",
                "source_url": company_facts_url(cik),
            })
    return sorted(
        rows,
        key=lambda row: (row["reference_date"], row["filed_at"], row["accession_number"]),
    )


def _duration_days(
    start: str | None,
    end: str,
) -> int | None:
    if start is None:
        return None

    return (
        date.fromisoformat(end)
        - date.fromisoformat(start)
    ).days


def classify_period(
    start: str | None,
    end: str,
) -> tuple[str, str | None]:
    """Classify an SEC fact by its economic period."""
    if start is None:
        month = date.fromisoformat(end).month

        labels = {
            3: "Q1",
            6: "Q2",
            9: "Q3",
            12: "FY",
        }

        return "INSTANT", labels.get(month)

    days = _duration_days(start, end)

    if days is None:
        raise ValueError("Duration could not be calculated.")

    end_month = date.fromisoformat(end).month

    if 75 <= days <= 105:
        quarters = {
            3: "Q1",
            6: "Q2",
            9: "Q3",
            12: "Q4",
        }

        return "QUARTER", quarters.get(end_month)

    if 150 <= days <= 200:
        return "YTD", "H1"

    if 240 <= days <= 290:
        return "YTD", "9M"

    if 330 <= days <= 380:
        return "FY", "FY"

    return "OTHER", None


def _economic_key(
    taxonomy: str,
    concept: str,
    unit: str,
    item: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        taxonomy,
        concept,
        unit,
        item.get("start"),
        item.get("end"),
    )


def normalize_company_facts(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize selected Company Facts and deduplicate filings."""
    facts = payload.get("facts", {})

    normalized: list[dict[str, Any]] = []

    for metric_id, mapping in SEC_CONCEPT_MAP.items():
        taxonomy = mapping["taxonomy"]
        concept_name = mapping["concept"]

        concept = (
            facts
            .get(taxonomy, {})
            .get(concept_name)
        )

        if not concept:
            continue

        for unit, observations in concept.get("units", {}).items():
            groups: dict[
                tuple[Any, ...],
                list[dict[str, Any]],
            ] = defaultdict(list)

            for item in observations:
                if item.get("form") not in ALLOWED_FORMS:
                    continue

                if not item.get("end"):
                    continue

                key = _economic_key(
                    taxonomy,
                    concept_name,
                    unit,
                    item,
                )

                groups[key].append(item)

            for items in groups.values():
                ordered = sorted(
                    items,
                    key=lambda x: (
                        x.get("filed", ""),
                        x.get("accn", ""),
                    ),
                )

                selected = ordered[-1]

                unique_values = {
                    item.get("val")
                    for item in ordered
                }

                first_reported = ordered[0]
                first_value = first_reported.get("val")
                selected_value = selected.get("val")

                value_change = None

                if (
                    isinstance(first_value, (int, float))
                    and isinstance(selected_value, (int, float))
                ):
                    value_change = selected_value - first_value

                period_type, period_label = classify_period(
                    selected.get("start"),
                    selected["end"],
                )

                normalized.append(
                    {
                        "metric_id": metric_id,
                        "taxonomy": taxonomy,
                        "concept": concept_name,
                        "unit": unit,
                        "value": selected.get("val"),
                        "period_start": selected.get("start"),
                        "period_end": selected["end"],
                        "reference_year": int(
                            selected["end"][:4]
                        ),
                        "period_type": period_type,
                        "period_label": period_label,
                        "form": selected.get("form"),
                        "filed_at": selected.get("filed"),
                        "accession_number": selected.get("accn"),
                        "frame": selected.get("frame"),
                        "source_fy": selected.get("fy"),
                        "source_fp": selected.get("fp"),
                        "occurrences": len(ordered),
                        "first_reported_value": first_value,
                        "first_filed_at": first_reported.get("filed"),
                        "first_accession_number": first_reported.get("accn"),
                        "has_value_change": len(unique_values) > 1,
                        "value_change": value_change,
                        "is_derived": False,
                    }
                )

    normalized.sort(
        key=lambda row: (
            row["metric_id"],
            row["period_end"],
            row["period_start"] or "",
        )
    )

    return normalized
