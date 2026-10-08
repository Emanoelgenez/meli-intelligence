"""Tests for qualifier-aware extended operational analytics."""

from __future__ import annotations

import pandas as pd
import pytest

from meli_intelligence.analytics.extended_operational import (
    build_extended_operational_analytics,
    calculate_extended_yoy,
    calculate_per_fintech_mau,
)


def _fact(metric: str, end: str, value: float, *, qualifier: str = "exact") -> dict:
    date = pd.Timestamp(end)
    return {
        "metric_id": metric,
        "scope": "total_portfolio" if metric != "aum" else "total",
        "period_start": pd.NaT,
        "period_end": date,
        "reference_year": date.year,
        "period_type": "INSTANT",
        "period_label": f"Q{(date.month - 1) // 3 + 1}",
        "value": value,
        "unit": "percent" if metric == "npl_15_90_total" else "USD",
        "value_qualifier": qualifier,
    }


def _mau(
    end: str,
    value: float = 88_000_000,
    *,
    unit: str = "users",
    definition_version: str | None = None,
) -> dict:
    date = pd.Timestamp(end)
    row = {
        "metric_id": "fintech_mau",
        "period_start": pd.NaT,
        "period_end": date,
        "reference_year": date.year,
        "period_type": "INSTANT",
        "period_label": f"Q{(date.month - 1) // 3 + 1}",
        "value": value,
        "unit": unit,
    }
    if definition_version is not None:
        row["definition_version"] = definition_version
    return row


def test_aum_yoy_requires_exact_values() -> None:
    facts = pd.DataFrame([
        _fact("aum", "2025-06-30", 20e9),
        _fact("aum", "2026-06-30", 23e9),
    ])
    result = calculate_extended_yoy(facts, "aum")
    assert result.iloc[0]["value"] == pytest.approx(15.0)
    assert result.iloc[0]["unit"] == "percent"
    assert bool(result.iloc[0]["is_derived"]) is True


@pytest.mark.parametrize("side", ["current", "prior"])
def test_aum_yoy_skips_approximate_input(side: str) -> None:
    qualifiers = {"current": "exact", "prior": "exact"}
    qualifiers[side] = "approximate"
    facts = pd.DataFrame([
        _fact("aum", "2025-06-30", 20e9, qualifier=qualifiers["prior"]),
        _fact("aum", "2026-06-30", 23e9, qualifier=qualifiers["current"]),
    ])
    assert calculate_extended_yoy(facts, "aum").empty


def test_credit_yoy_excludes_lower_bound_but_q1_exact_is_valid() -> None:
    facts = pd.DataFrame([
        _fact("credit_portfolio", "2025-03-31", 12e9),
        _fact("credit_portfolio", "2026-03-31", 15e9),
        _fact("credit_portfolio", "2025-06-30", 13e9),
        _fact("credit_portfolio", "2026-06-30", 16e9, qualifier="lower_bound"),
    ])
    result = calculate_extended_yoy(facts, "credit_portfolio")
    assert result["period_end"].tolist() == [pd.Timestamp("2026-03-31")]
    assert result.iloc[0]["value"] == pytest.approx(25.0)


def test_npl_change_is_percentage_points_and_q4_missing() -> None:
    facts = pd.DataFrame([
        _fact("npl_15_90_total", "2025-03-31", 8.2),
        _fact("npl_15_90_total", "2026-03-31", 8.0),
        _fact("npl_15_90_total", "2025-06-30", 6.7),
        _fact("npl_15_90_total", "2026-06-30", 7.0),
        _fact("npl_15_90_total", "2024-12-31", 6.0),
        _fact("npl_15_90_total", "2026-12-31", 6.2),
    ])
    result = calculate_extended_yoy(
        facts, "npl_15_90_total", output_metric_id="npl_15_90_yoy_change_pp",
        percentage_point_change=True,
    )
    values = result.set_index("period_label")["value"]
    assert values["Q1"] == pytest.approx(-0.2)
    assert values["Q2"] == pytest.approx(0.3)
    assert result["unit"].eq("percentage_points").all()
    assert not result["period_end"].eq(pd.Timestamp("2025-12-31")).any()


def test_ambiguous_yoy_source_key_fails_explicitly() -> None:
    facts = pd.DataFrame([
        _fact("aum", "2025-06-30", 20e9),
        _fact("aum", "2025-06-30", 21e9),
        _fact("aum", "2026-06-30", 23e9),
    ])
    with pytest.raises(ValueError, match="Ambiguous YoY source periods"):
        calculate_extended_yoy(facts, "aum")


def test_aum_per_mau_requires_exact_date_and_exact_aum() -> None:
    facts = pd.DataFrame([
        _fact("aum", "2026-06-30", 23e9),
        _fact("aum", "2025-06-30", 20e9, qualifier="approximate"),
    ])
    operational = pd.DataFrame([_mau("2026-06-30"), _mau("2025-06-29")])
    result = calculate_per_fintech_mau(facts, operational, "aum")
    assert len(result) == 1
    assert result.iloc[0]["value"] == pytest.approx(261.36363636)
    assert result.iloc[0]["period_end"] == pd.Timestamp("2026-06-30")
    assert "denominator=reported_fintech_mau" in result.iloc[0]["definition_context"]


@pytest.mark.parametrize(
    ("numerator_unit", "mau_unit"),
    [("EUR", "users"), ("USD", "customers")],
)
def test_aum_per_mau_requires_semantically_valid_units(
    numerator_unit: str,
    mau_unit: str,
) -> None:
    numerator = _fact("aum", "2026-06-30", 23e9)
    numerator["unit"] = numerator_unit
    result = calculate_per_fintech_mau(
        pd.DataFrame([numerator]),
        pd.DataFrame([_mau("2026-06-30", unit=mau_unit)]),
        "aum",
    )
    assert result.empty


def test_aum_per_mau_preserves_optional_mau_definition_version() -> None:
    result = calculate_per_fintech_mau(
        pd.DataFrame([_fact("aum", "2026-06-30", 23e9)]),
        pd.DataFrame([_mau("2026-06-30", definition_version="v2_recast")]),
        "aum",
    )
    context = result.iloc[0]["definition_context"]
    assert "mau_definition_version=v2_recast" in context


def test_aum_per_mau_works_without_mau_definition_version() -> None:
    result = calculate_per_fintech_mau(
        pd.DataFrame([_fact("aum", "2026-06-30", 23e9)]),
        pd.DataFrame([_mau("2026-06-30")]),
        "aum",
    )
    assert len(result) == 1
    assert "denominator=reported_fintech_mau" in result.iloc[0]["definition_context"]
    assert "mau_definition_version" not in result.iloc[0]["definition_context"]


def test_credit_portfolio_per_mau_excludes_lower_bound() -> None:
    facts = pd.DataFrame([
        _fact("credit_portfolio", "2026-06-30", 16e9, qualifier="lower_bound"),
    ])
    operational = pd.DataFrame([_mau("2026-06-30")])
    assert calculate_per_fintech_mau(
        facts, operational, "credit_portfolio"
    ).empty


def test_build_returns_only_supported_derived_metrics() -> None:
    extended = pd.DataFrame([
        _fact("aum", "2025-06-30", 20e9),
        _fact("aum", "2026-06-30", 23e9),
        _fact("credit_portfolio", "2025-06-30", 13e9),
        _fact("credit_portfolio", "2026-06-30", 16e9, qualifier="lower_bound"),
    ])
    operational = pd.DataFrame([_mau("2026-06-30")])
    result = build_extended_operational_analytics(extended, operational)
    assert set(result["metric_id"]) == {"aum_yoy_growth", "aum_per_fintech_mau"}
