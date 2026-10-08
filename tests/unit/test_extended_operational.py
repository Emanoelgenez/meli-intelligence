"""Tests for extended operational extraction."""

from __future__ import annotations

from meli_intelligence.transformations.extended_operational import (
    parse_extended_release,
)


def _metadata() -> dict:
    return {
        "source": "SEC EDGAR earnings release exhibit",
        "source_url": "https://example.com/release.htm",
        "filing_date": "2026-08-05",
        "accession_number": "0001099590-26-000021",
    }


def test_q2_2026_extended_facts() -> None:
    html = """
    <html><body>
    Fintech Services continued to scale.
    AUM reached $23bn, up 68% YoY.
    Our credit portfolio is showing a similar dynamic as it
    surpassed $16bn in Q2'26, growing 75% YoY.
    In Q2'26, the 15-90 day NPL was 7.0% for the portfolio
    as a whole, and 4.6% for the credit card specifically.
    MELI+ subscriber growth was up 72% YoY in Q2'26.
    Ecosystemic users grew 37% YoY in Q2'26.
    Advertising surpassed 10% share of the digital advertising
    market in Latin America.
    Fulfillment volume grew strongly.
    </body></html>
    """

    facts, evidence = (
        parse_extended_release(
            html,
            _metadata(),
            reference_period="2026-06-30",
        )
    )

    by_metric = {
        row["metric_id"]: row
        for row in facts
    }

    assert (
        by_metric["aum"]["value"]
        == 23_000_000_000
    )

    assert (
        by_metric[
            "credit_portfolio"
        ]["value"]
        == 16_000_000_000
    )

    assert (
        by_metric[
            "credit_portfolio"
        ]["value_qualifier"]
        == "lower_bound"
    )

    assert (
        by_metric[
            "npl_15_90_total"
        ]["value"]
        == 7.0
    )

    assert {
        row["evidence_type"]
        for row in evidence
    } == {
        "meli_plus",
        "ecosystemic_users",
        "advertising",
        "fulfillment",
    }


def test_approximate_aum_is_preserved() -> None:
    html = """
    <html><body>
    AUM reached almost $20bn, up 77% YoY.
    </body></html>
    """

    facts, _ = parse_extended_release(
        html,
        _metadata(),
        reference_period="2026-03-31",
    )

    row = next(
        row
        for row in facts
        if row["metric_id"] == "aum"
    )

    assert row["value"] == 20_000_000_000
    assert (
        row["value_qualifier"]
        == "approximate"
    )


def test_q1_2026_total_npl_wording() -> None:
    html = """
    <html><body>
    Asset quality remained solid, with the 15-90 day NPL
    of 8.0% broadly stable YoY, reflecting the continued
    strong performance of our underwriting models.
    </body></html>
    """

    facts, _ = parse_extended_release(
        html,
        _metadata(),
        reference_period="2026-03-31",
    )

    npl = [
        row
        for row in facts
        if row["metric_id"]
        == "npl_15_90_total"
    ]

    assert len(npl) == 1
    assert npl[0]["value"] == 8.0
    assert (
        npl[0]["scope"]
        == "total_portfolio"
    )


def test_card_npl_is_not_total_npl() -> None:
    html = """
    <html><body>
    The credit card's 15-90 NPL reached a historic low
    of 4.4% in Q4'25.
    </body></html>
    """

    facts, _ = parse_extended_release(
        html,
        _metadata(),
        reference_period="2025-12-31",
    )

    assert not any(
        row["metric_id"]
        == "npl_15_90_total"
        for row in facts
    )