"""Tests for SEC Company Facts normalization."""

from __future__ import annotations

from meli_intelligence.transformations.sec_companyfacts import (
    classify_period,
    normalize_company_facts,
    normalize_shares_outstanding,
)


def test_classify_instant() -> None:
    assert classify_period(
        None,
        "2026-06-30",
    ) == ("INSTANT", "Q2")


def test_classify_quarter() -> None:
    assert classify_period(
        "2026-04-01",
        "2026-06-30",
    ) == ("QUARTER", "Q2")


def test_classify_ytd_half_year() -> None:
    assert classify_period(
        "2026-01-01",
        "2026-06-30",
    ) == ("YTD", "H1")


def test_classify_ytd_nine_months() -> None:
    assert classify_period(
        "2025-01-01",
        "2025-09-30",
    ) == ("YTD", "9M")


def test_classify_fiscal_year() -> None:
    assert classify_period(
        "2025-01-01",
        "2025-12-31",
    ) == ("FY", "FY")


def test_latest_filing_wins_for_same_economic_period() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 100,
                                "fy": 2025,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2025-05-01",
                                "accn": "old",
                            },
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 100,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "accn": "new",
                            },
                        ]
                    }
                }
            }
        }
    }

    rows = normalize_company_facts(payload)

    assert len(rows) == 1

    row = rows[0]

    assert row["reference_year"] == 2025
    assert row["source_fy"] == 2026
    assert row["accession_number"] == "new"
    assert row["occurrences"] == 2
    assert row["has_value_change"] is False


def test_value_change_is_flagged() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 100,
                                "form": "10-Q",
                                "filed": "2025-05-01",
                                "accn": "old",
                            },
                            {
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "val": 105,
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "accn": "new",
                            },
                        ]
                    }
                }
            }
        }
    }

    rows = normalize_company_facts(payload)

    assert len(rows) == 1
    assert rows[0]["value"] == 105
    assert rows[0]["has_value_change"] is True
    assert rows[0]["first_reported_value"] == 100
    assert rows[0]["value_change"] == 5


def test_non_financial_forms_are_ignored() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 100,
                                "form": "10-K",
                                "filed": "2026-02-01",
                                "accn": "10k",
                            },
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 100,
                                "form": "DEF 14A",
                                "filed": "2026-04-01",
                                "accn": "proxy",
                            },
                        ]
                    }
                }
            }
        }
    }

    rows = normalize_company_facts(payload)

    assert len(rows) == 1
    assert rows[0]["form"] == "10-K"
    assert rows[0]["accession_number"] == "10k"


def test_explicit_dei_shares_outstanding_is_preserved_as_instant_company_fact() -> None:
    payload = {
        "cik": 1099590,
        "entityName": "MercadoLibre, Inc.",
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "end": "2025-12-31", "val": 51000000,
                                "filed": "2026-02-20", "accn": "0001099590-26-000001",
                                "form": "10-K",
                            },
                            {
                                "start": "2025-01-01", "end": "2025-12-31", "val": 1,
                                "filed": "2026-02-20", "accn": "duration", "form": "10-K",
                            },
                            {
                                "end": "2025-12-31", "val": 2,
                                "filed": "2026-02-20", "accn": "proxy", "form": "DEF 14A",
                            },
                        ]
                    }
                }
            }
        },
    }

    rows = normalize_shares_outstanding(payload)

    assert len(rows) == 1
    assert rows[0]["entity"] == "MercadoLibre, Inc."
    assert rows[0]["metric_id"] == "shares_outstanding"
    assert rows[0]["source_metric_id"] == "dei:EntityCommonStockSharesOutstanding"
    assert rows[0]["taxonomy"] == "dei"
    assert rows[0]["concept"] == "EntityCommonStockSharesOutstanding"
    assert rows[0]["reference_date"].isoformat() == "2025-12-31"
    assert rows[0]["filed_at"].isoformat() == "2026-02-20"
    assert rows[0]["value"] == 51000000
    assert rows[0]["unit"] == "shares"
    assert rows[0]["accession_number"] == "0001099590-26-000001"
    assert rows[0]["source"] == "SEC EDGAR Company Facts API"
    assert rows[0]["source_url"].endswith("CIK0001099590.json")


def test_shares_outstanding_extraction_is_empty_when_official_tag_is_absent() -> None:
    payload = {"cik": 1099590, "entityName": "MercadoLibre, Inc.", "facts": {"us-gaap": {}}}
    assert normalize_shares_outstanding(payload) == []
