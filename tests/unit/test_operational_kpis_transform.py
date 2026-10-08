"""Tests for MercadoLibre operational KPI parsing."""

from __future__ import annotations

import pytest

from meli_intelligence.transformations.operational_kpis import (
    parse_operational_release,
)


def _metadata() -> dict:
    return {
        "source": "SEC EDGAR Exhibit 99.1",
        "source_url": "https://example.com/release.htm",
        "filing_date": "2026-08-05",
        "sec_report_date": "2026-08-05",
        "accession_number": (
            "0001099590-26-000021"
        ),
    }


def _q2_2026_html(
    *,
    mau_quarter: int = 88,
) -> str:
    return f"""
    <html>
      <body>
        <font style="font-size:1pt;color:white">
          The following table summarizes certain key performance
          metrics for the six and three-month periods ended
          June 30, 2026 and 2025:

          Six Months Ended June 30,
          Three Months Ended June 30,
          (IN MILLIONS, except %)
          2026 2025 2026 2025

          Fintech monthly active users
          88 68 {mau_quarter} 68

          Unique active buyers
          117 90 89 71

          Gross merchandise volume
          40,877 28,588 21,926 15,258

          Number of items sold
          1,517 1,042 795 550

          Total payment volume
          188,138 122,905 100,952 64,602

          Acquiring total payment volume
          120,072 84,682 64,079 44,365

          Total payment transactions
          9,821 6,951 5,181 3,607

          NIMAL
          19.4 % 22.8 % 20.7 % 23.0 %

          Capital expenditures
          712 543 441 287

          Definition of Selected Metrics

          Fintech monthly active users:
          has an active insurance policy and has an outstanding
          loan up to date or non performing below 90 days.

          Unique active buyers:
          From the second quarter of 2025 onwards, we have included
          food delivery transactions in the current indicator.

          Gross merchandise volume:
          From the second quarter of 2025 onwards, we have included
          food delivery transactions in the current indicator.

          Total payment transactions:
          excluding peer-to-peer transactions.

          Total payment volume:
          excluding peer-to-peer transactions.
        </font>
      </body>
    </html>
    """


def test_parse_q2_operational_release() -> None:
    rows = parse_operational_release(
        _q2_2026_html(),
        _metadata(),
    )

    assert len(rows) == 30

    current_gmv = [
        row
        for row in rows
        if (
            row["metric_id"] == "gmv"
            and not row[
                "is_comparative"
            ]
        )
    ]

    assert len(current_gmv) == 2

    h1 = next(
        row
        for row in current_gmv
        if row["period_type"] == "YTD"
    )

    q2 = next(
        row
        for row in current_gmv
        if row[
            "period_type"
        ] == "QUARTER"
    )

    assert h1["period_label"] == "H1"
    assert (
        h1["value"]
        == 40_877_000_000
    )

    assert q2["period_label"] == "Q2"
    assert (
        q2["value"]
        == 21_926_000_000
    )

    assert (
        q2["definition_version"]
        == "v2_food_delivery"
    )


def test_fintech_mau_is_instant_and_deduplicated() -> None:
    rows = parse_operational_release(
        _q2_2026_html(),
        _metadata(),
    )

    mau = [
        row
        for row in rows
        if row["metric_id"] == "fintech_mau"
    ]

    assert len(mau) == 2

    current = next(
        row
        for row in mau
        if not row[
            "is_comparative"
        ]
    )

    assert (
        current["period_type"]
        == "INSTANT"
    )

    assert (
        current["period_start"]
        is None
    )

    assert (
        current["period_end"]
        == "2026-06-30"
    )

    assert (
        current["value"]
        == 88_000_000
    )

    assert (
        current["definition_version"]
        == (
            "v2_active_policy_and_current_loan"
        )
    )


def test_fintech_mau_duplicate_columns_must_agree() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "Fintech MAU duplicated table columns "
            "do not agree"
        ),
    ):
        parse_operational_release(
            _q2_2026_html(
                mau_quarter=87
            ),
            _metadata(),
        )


def test_definition_cutoffs_use_economic_period() -> None:
    rows = parse_operational_release(
        _q2_2026_html(),
        _metadata(),
    )

    buyers_q2_2025 = next(
        row
        for row in rows
        if (
            row["metric_id"]
            == "unique_active_buyers"
            and row["period_type"]
            == "QUARTER"
            and row["reference_year"]
            == 2025
        )
    )

    mau_2025 = next(
        row
        for row in rows
        if (
            row["metric_id"]
            == "fintech_mau"
            and row["reference_year"]
            == 2025
        )
    )

    assert (
        buyers_q2_2025[
            "definition_version"
        ]
        == "v2_food_delivery"
    )

    assert (
        mau_2025[
            "definition_version"
        ]
        == "v1_transaction_action"
    )


def test_food_delivery_definition_versions() -> None:
    rows = parse_operational_release(
        _q2_2026_html(),
        _metadata(),
    )

    q2_2025_items = next(
        row
        for row in rows
        if (
            row["metric_id"] == "items_sold"
            and row["reference_year"] == 2025
            and row["period_type"] == "QUARTER"
        )
    )

    h1_2025_items = next(
        row
        for row in rows
        if (
            row["metric_id"] == "items_sold"
            and row["reference_year"] == 2025
            and row["period_type"] == "YTD"
        )
    )

    h1_2025_buyers = next(
        row
        for row in rows
        if (
            row["metric_id"] == "unique_active_buyers"
            and row["reference_year"] == 2025
            and row["period_type"] == "YTD"
        )
    )

    h1_2025_gmv = next(
        row
        for row in rows
        if (
            row["metric_id"] == "gmv"
            and row["reference_year"] == 2025
            and row["period_type"] == "YTD"
        )
    )

    assert (
        q2_2025_items["definition_version"]
        == "v2_food_delivery"
    )

    for row in (
        h1_2025_items,
        h1_2025_buyers,
        h1_2025_gmv,
    ):
        assert (
            row["definition_version"]
            == "v2_food_delivery_transition_2025"
        )


def test_q4_2024_recast_p2p_definition() -> None:
    html = """
    <html>
      <body>
        The following table summarizes certain key performance
        metrics for the twelve and three-month periods ended
        December 31, 2024 and 2023.

        Years Ended December 31,
        Three Months Ended December 31,
        (IN MILLIONS, except %)
        2024 2023 2024 2023

        Fintech monthly active users
        61 46 61 46

        Unique active buyers
        100 85 67 54

        Gross merchandise volume
        51,467 44,749 14,548 13,450

        Number of items sold
        1,787 1,404 525 413

        Total payment volume (2)
        196,660 146,738 58,914 44,460

        Acquiring total payment volume
        142,200 115,953 41,833 34,732

        Total payment transactions (2)
        11,355 7,595 3,325 2,320

        NIMAL
        28.2 % 36.2 % 27.6 % 39.8 %

        Capital expenditures
        860 509 305 180

        Total payment volume and transactions for the twelve
        and three-month periods ended December 31, 2023,
        have been recast to exclude peer-to-peer transactions.
    </html>
    """

    rows = parse_operational_release(
        html,
        {
            **_metadata(),
            "filing_date": "2025-02-20",
            "accession_number": (
                "0001099590-25-000004"
            ),
        },
    )

    old_tpv = [
        row
        for row in rows
        if (
            row["metric_id"] == "tpv"
            and row["reference_year"]
            == 2023
        )
    ]

    assert len(old_tpv) == 2

    assert all(
        row["definition_version"]
        == "v2_recast_excludes_p2p"
        for row in old_tpv
    )