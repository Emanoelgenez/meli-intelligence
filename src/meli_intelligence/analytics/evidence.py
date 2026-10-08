"""Deterministic source-grounded normalization of evidence facts."""

from __future__ import annotations

import hashlib
import re

import pandas as pd


METHODOLOGY_VERSION = "1"
DOMAIN_BY_EVIDENCE_TYPE = {
    "meli_plus": "Ecosystem",
    "ecosystemic_users": "Ecosystem",
    "advertising": "Ads",
    "fulfillment": "Logistics",
}
_CLAIM_RULES = {
    "growth": re.compile(
        r"\b(?:grew|growth|growing|grow|increased|increase|expanded|expansion)\b"
        r"|\bup\s+(?:by\s+\d+(?:\.\d+)?(?:\s*(?:%|ppts?))?"
        r"|\d+(?:\.\d+)?\s*(?:%|ppts?))(?!\w)",
        re.IGNORECASE,
    ),
    "share": re.compile(
        r"\b(?:share|penetration|ppts)\b|%\s+of\b",
        re.IGNORECASE,
    ),
    "engagement": re.compile(
        r"\b(?:ecosystemic users?|active behavior|daily active|"
        r"bought|purchased|categories bought|used together|use together|"
        r"frequency of use|cross[- ]use)\b",
        re.IGNORECASE,
    ),
    "operational": re.compile(
        r"\b(?:fulfillment|delivery|shipping|shipments?|cost|operational volume)\b",
        re.IGNORECASE,
    ),
}


def classify_claim_kind(source_statement: str) -> str:
    """Classify only unambiguous explicit lexical signals."""
    matches = [
        kind for kind, pattern in _CLAIM_RULES.items()
        if pattern.search(source_statement)
    ]
    return matches[0] if len(matches) == 1 else "other"


def _observation_id(evidence_id: str) -> str:
    return hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()


def normalize_evidence_facts(evidence_facts: pd.DataFrame) -> pd.DataFrame:
    """Map each FACT row to one source-preserving OBSERVATION row."""
    required = {
        "evidence_id", "evidence_type", "reference_period", "statement",
        "source_url", "filing_date", "accession_number",
    }
    missing = required.difference(evidence_facts.columns)
    if missing:
        raise ValueError(f"Evidence facts missing columns: {sorted(missing)}")
    if evidence_facts["evidence_id"].duplicated().any():
        raise ValueError("Evidence IDs must be unique to normalize observations.")
    rows = []
    for row in evidence_facts.to_dict(orient="records"):
        evidence_type = str(row["evidence_type"])
        if evidence_type not in DOMAIN_BY_EVIDENCE_TYPE:
            raise ValueError(f"Unsupported evidence type: {evidence_type}")
        statement = re.sub(r"\s+", " ", str(row["statement"])).strip()
        rows.append(
            {
                "observation_id": _observation_id(str(row["evidence_id"])),
                "evidence_id": row["evidence_id"],
                "evidence_type": evidence_type,
                "business_domain": DOMAIN_BY_EVIDENCE_TYPE[evidence_type],
                "reference_period": row["reference_period"],
                "observation_text": statement,
                "source_statement": statement,
                "source_url": row["source_url"],
                "filing_date": row["filing_date"],
                "accession_number": row["accession_number"],
                "methodology_version": METHODOLOGY_VERSION,
                "evidence_stage": "OBSERVATION",
                "is_interpretation": False,
                "claim_kind": classify_claim_kind(statement),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "observation_id", "evidence_id", "evidence_type", "business_domain",
            "reference_period", "observation_text", "source_statement", "source_url",
            "filing_date", "accession_number", "methodology_version", "evidence_stage",
            "is_interpretation", "claim_kind",
        ],
    )
