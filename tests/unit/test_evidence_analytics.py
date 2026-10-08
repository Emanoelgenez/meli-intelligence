"""Tests for deterministic FACT to OBSERVATION normalization."""

from __future__ import annotations

import pandas as pd

from meli_intelligence.analytics.evidence import (
    classify_claim_kind,
    normalize_evidence_facts,
)


def _evidence(evidence_type: str, statement: str, evidence_id: str = "fact-1") -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "reference_period": "2026-06-30",
        "statement": statement,
        "source_url": "https://example.com/source",
        "filing_date": "2026-08-05",
        "accession_number": "0000000000-26-000001",
    }


def test_each_fact_yields_one_deterministic_observation() -> None:
    facts = pd.DataFrame([
        _evidence(kind, f"Fact for {kind}.", kind)
        for kind in ("meli_plus", "ecosystemic_users", "advertising", "fulfillment")
    ])
    first = normalize_evidence_facts(facts)
    second = normalize_evidence_facts(facts)
    assert len(first) == len(facts)
    assert first["observation_id"].tolist() == second["observation_id"].tolist()
    assert first["business_domain"].tolist() == [
        "Ecosystem", "Ecosystem", "Ads", "Logistics"
    ]
    assert first["evidence_stage"].eq("OBSERVATION").all()
    assert not first["is_interpretation"].any()
    assert not {"interpretation", "hypothesis", "recommendation"}.intersection(first.columns)


def test_observation_preserves_source_statement_whitespace_only() -> None:
    observation = normalize_evidence_facts(pd.DataFrame([
        _evidence("ecosystemic_users", "  Ecosystemic   users grew 37% YoY.  ")
    ])).iloc[0]
    assert observation["source_statement"] == "Ecosystemic users grew 37% YoY."
    assert observation["observation_text"] == observation["source_statement"]


def test_claim_kind_rules_and_ambiguous_fallback() -> None:
    assert classify_claim_kind("AUM grew 20%.") == "growth"
    assert classify_claim_kind("Reached 10% share of the market.") == "share"
    assert classify_claim_kind("Users bought across more categories.") == "engagement"
    assert classify_claim_kind("Fulfillment delivery volume was 10 million.") == "operational"
    assert classify_claim_kind("AUM grew and market share increased.") == "other"
    assert classify_claim_kind("Statement with no explicit signal.") == "other"


def test_up_is_growth_only_with_explicit_numeric_change() -> None:
    assert classify_claim_kind("Subscribers were up 72% YoY.") == "growth"
    assert classify_claim_kind("Loans up to 90 days past due.") == "other"
    assert classify_claim_kind("Exposure of up to $10bn.") == "other"
    assert classify_claim_kind("Revenue was up by 15%.") == "growth"
    assert classify_claim_kind("Revenue was up by 15.") == "growth"
    assert classify_claim_kind("Share was up 8ppts.") == "other"
