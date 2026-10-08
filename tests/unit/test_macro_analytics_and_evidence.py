"""Offline tests for deterministic Macro analytics and evidence boundaries."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.analytics.macro import (
    MACRO_ANALYTICS_COLUMNS,
    build_macro_analytics,
    build_macro_direction_flags,
    pearson_correlation,
)
from meli_intelligence.analytics.macro_evidence import build_macro_observations
from meli_intelligence.query.macro_analytics import query_macro_analytics, query_macro_evidence
from meli_intelligence.storage import macro_analytics as storage
from meli_intelligence.storage.macro_analytics import (
    read_macro_analytics,
    read_macro_evidence,
    write_macro_analytics,
    write_macro_evidence,
)


def _source_row(metric_id: str, reference_date: date, value: float, unit: str, frequency: str) -> dict:
    return {
        "metric_id": metric_id,
        "source_series_id": f"source:{metric_id}",
        "reference_date": reference_date,
        "value": value,
        "unit": unit,
        "frequency": frequency,
        "source": f"Official source for {metric_id}",
        "source_url": f"https://official.example/{metric_id}",
        "retrieved_at": "2026-10-05T00:00:00+00:00",
        "ingestion_version": "1",
    }


def _macro_facts() -> pd.DataFrame:
    rows = [
        _source_row("selic_target_annual", date(2023, 12, 28), 11.75, "percent_per_year", "daily"),
        _source_row("selic_target_annual", date(2024, 1, 2), 12.25, "percent_per_year", "daily"),
        _source_row("selic_target_annual", date(2024, 1, 15), 12.25, "percent_per_year", "daily"),
        _source_row("ipca_12m_change", date(2023, 12, 31), 6.0, "percent", "monthly"),
        _source_row("ipca_12m_change", date(2024, 1, 31), 6.2, "percent", "monthly"),
        _source_row("ipca_12m_change", date(2024, 2, 29), 6.2, "percent", "monthly"),
        _source_row("usd_brl_sell_rate", date(2023, 12, 29), 4.8, "brl_per_usd", "daily"),
        _source_row("usd_brl_sell_rate", date(2024, 1, 31), 4.9, "brl_per_usd", "daily"),
        _source_row("usd_brl_sell_rate", date(2024, 3, 28), 5.0, "brl_per_usd", "daily"),
        _source_row("household_free_credit_balance", date(2023, 2, 28), 100.0, "million_brl", "monthly"),
        _source_row("household_free_credit_balance", date(2024, 2, 29), 110.0, "million_brl", "monthly"),
        _source_row("household_free_credit_npl_90d_rate", date(2023, 2, 28), 6.1, "percent", "monthly"),
        _source_row("household_free_credit_npl_90d_rate", date(2024, 2, 29), 6.8, "percent", "monthly"),
        _source_row("ibc_br_activity_sa_index", date(2023, 12, 31), 100.0, "index", "monthly"),
        _source_row("ibc_br_activity_sa_index", date(2024, 1, 31), 101.0, "index", "monthly"),
        _source_row("ibc_br_activity_sa_index", date(2024, 3, 31), 105.0, "index", "monthly"),
        _source_row("unemployment_rate_rolling_3m", date(2023, 12, 31), 7.4, "percent", "rolling_3m_monthly"),
        _source_row("unemployment_rate_rolling_3m", date(2024, 1, 31), 7.5, "percent", "rolling_3m_monthly"),
        _source_row("unemployment_rate_rolling_3m", date(2024, 2, 29), 7.3, "percent", "rolling_3m_monthly"),
        _source_row("pix_transactions_count_monthly", date(2023, 2, 28), 1000.0, "transactions", "monthly"),
        _source_row("pix_transactions_count_monthly", date(2024, 2, 29), 1250.0, "transactions", "monthly"),
        _source_row("pix_transactions_value_monthly", date(2023, 2, 28), 200.0, "brl", "monthly"),
        _source_row("pix_transactions_value_monthly", date(2024, 2, 29), 250.0, "brl", "monthly"),
        _source_row("retail_sales_volume_mom_sa", date(2024, 2, 29), 0.8, "percent", "monthly"),
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def macro_facts() -> pd.DataFrame:
    return _macro_facts()


@pytest.fixture
def analytics(macro_facts: pd.DataFrame) -> pd.DataFrame:
    return build_macro_analytics(macro_facts)


def _one(frame: pd.DataFrame, metric_id: str, ref: date) -> pd.Series:
    rows = frame.loc[(frame.metric_id == metric_id) & (frame.reference_date == ref)]
    assert len(rows) == 1
    return rows.iloc[0]


def test_monthly_yoy_leap_february_match_and_previous_calendar_month(analytics: pd.DataFrame) -> None:
    credit = _one(analytics, "household_free_credit_balance_yoy_growth", date(2024, 2, 29))
    pix_count = _one(analytics, "pix_transactions_count_yoy_growth", date(2024, 2, 29))
    pix_value = _one(analytics, "pix_transactions_value_yoy_growth", date(2024, 2, 29))
    assert credit.value == pytest.approx(10.0)
    assert credit.previous_reference_date == date(2023, 2, 28)
    assert pix_count.value == pytest.approx(25.0)
    assert pix_value.value == pytest.approx(25.0)
    assert "same_month_previous_year" in credit.definition_context
    selic = _one(analytics, "selic_target_change_pp", date(2024, 1, 2))
    assert selic.previous_reference_date == date(2023, 12, 28)


def test_yoy_february_2025_matches_leap_year_february_2024() -> None:
    facts = pd.DataFrame([
        _source_row("pix_transactions_count_monthly", date(2024, 2, 29), 100, "transactions", "monthly"),
        _source_row("pix_transactions_count_monthly", date(2025, 2, 28), 125, "transactions", "monthly"),
    ])
    derived = build_macro_analytics(facts)
    row = _one(derived, "pix_transactions_count_yoy_growth", date(2025, 2, 28))
    assert row.value == pytest.approx(25.0)
    assert row.previous_reference_date == date(2024, 2, 29)


def test_yoy_missing_prior_and_mom_missing_calendar_month_are_omitted(analytics: pd.DataFrame) -> None:
    assert not ((analytics.metric_id == "pix_transactions_count_yoy_growth") & (analytics.reference_date == date(2023, 2, 28))).any()
    assert not ((analytics.metric_id == "ibc_br_activity_mom_change_pct") & (analytics.reference_date == date(2024, 3, 31))).any()
    assert not ((analytics.metric_id == "usd_brl_monthly_change_pct") & (analytics.reference_date == date(2024, 3, 31))).any()
    january = _one(analytics, "ibc_br_activity_mom_change_pct", date(2024, 1, 31))
    assert january.value == pytest.approx(1.0)
    assert january.previous_reference_date == date(2023, 12, 31)


def test_duplicate_macro_economic_key_fails(macro_facts: pd.DataFrame) -> None:
    duplicate = pd.concat([macro_facts, macro_facts.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate Macro Silver economic key"):
        build_macro_analytics(duplicate)


def test_selic_changes_are_temporal_and_have_descriptive_flags(analytics: pd.DataFrame) -> None:
    assert _one(analytics, "selic_target_change_pp", date(2024, 1, 2)).value == pytest.approx(0.5)
    unchanged = _one(analytics, "selic_target_change_pp", date(2024, 1, 15))
    assert unchanged.value == 0
    assert unchanged.direction_value == "unchanged"
    reverse = pd.DataFrame([
        _source_row("selic_target_annual", date(2024, 1, 2), 11.5, "percent_per_year", "daily"),
        _source_row("selic_target_annual", date(2024, 1, 1), 12.0, "percent_per_year", "daily"),
    ])
    row = _one(build_macro_analytics(reverse), "selic_target_change_pp", date(2024, 1, 2))
    assert row.value == pytest.approx(-0.5)
    assert row.direction_value == "falling"


def test_ipca_acceleration_deceleration_unchanged_and_missing_month(analytics: pd.DataFrame) -> None:
    assert _one(analytics, "ipca_12m_change_pp", date(2024, 1, 31)).direction_value == "accelerating"
    assert _one(analytics, "ipca_12m_change_pp", date(2024, 2, 29)).direction_value == "unchanged"
    reverse = pd.DataFrame([
        _source_row("ipca_12m_change", date(2023, 12, 31), 6.2, "percent", "monthly"),
        _source_row("ipca_12m_change", date(2024, 1, 31), 6.0, "percent", "monthly"),
    ])
    assert _one(build_macro_analytics(reverse), "ipca_12m_change_pp", date(2024, 1, 31)).direction_value == "decelerating"
    missing_previous = pd.DataFrame([_source_row("ipca_12m_change", date(2024, 3, 31), 6.1, "percent", "monthly")])
    assert build_macro_analytics(missing_previous).empty


def test_fx_uses_last_available_quote_then_calendar_month_end(analytics: pd.DataFrame) -> None:
    month_end = _one(analytics, "usd_brl_month_end", date(2023, 12, 31))
    assert month_end.value == pytest.approx(4.8)
    assert month_end.source_reference_date == date(2023, 12, 29)
    assert month_end.unit == "brl_per_usd"
    monthly_change = _one(analytics, "usd_brl_monthly_change_pct", date(2024, 1, 31))
    assert monthly_change.value == pytest.approx((4.9 / 4.8 - 1) * 100)
    assert monthly_change.direction_value == "depreciating_brl"
    assert not ((analytics.metric_id == "usd_brl_monthly_change_pct") & (analytics.reference_date == date(2024, 3, 31))).any()


def test_credit_zero_denominator_is_omitted_and_npl_is_percentage_points(analytics: pd.DataFrame) -> None:
    zero = pd.DataFrame([
        _source_row("household_free_credit_balance", date(2023, 2, 28), 0, "million_brl", "monthly"),
        _source_row("household_free_credit_balance", date(2024, 2, 29), 110, "million_brl", "monthly"),
    ])
    assert build_macro_analytics(zero).empty
    npl = _one(analytics, "household_free_credit_npl_90d_yoy_change_pp", date(2024, 2, 29))
    assert npl.value == pytest.approx(0.7)
    assert npl.unit == "percentage_points"
    assert "greater_than_90_days" in npl.definition_context
    assert "not_comparable_to_MELI_15_to_90_day_NPL" in npl.definition_context


def test_ibc_and_unemployment_preserve_semantics(analytics: pd.DataFrame) -> None:
    ibc = _one(analytics, "ibc_br_activity_mom_change_pct", date(2024, 1, 31))
    assert ibc.value == pytest.approx(1.0)
    assert "seasonally_adjusted_economic_activity" in ibc.definition_context
    assert "GDP" not in ibc.definition_context and "PIB" not in ibc.definition_context
    unemployment = _one(analytics, "unemployment_rate_change_pp", date(2024, 1, 31))
    assert unemployment.value == pytest.approx(0.1)
    assert unemployment.unit == "percentage_points"
    assert "three_month_rolling_windows_overlap" in unemployment.definition_context
    assert "not_independent_samples" in unemployment.definition_context
    assert unemployment.frequency == "rolling_3m_monthly"


def test_analytics_output_has_unique_finite_auditable_values(analytics: pd.DataFrame) -> None:
    assert list(analytics.columns) == MACRO_ANALYTICS_COLUMNS
    assert not analytics.duplicated(["metric_id", "reference_date"]).any()
    assert analytics.value.notna().all()
    assert analytics.value.map(lambda value: pd.notna(value) and abs(float(value)) != float("inf")).all()
    assert analytics.source_metric_id.notna().all()
    assert analytics.definition_context.str.len().gt(0).all()
    assert analytics.analytics_kind.str.len().gt(0).all()
    def units_for(metric_id: str) -> set[str]:
        return set(analytics.loc[analytics["metric_id"] == metric_id, "unit"])

    assert units_for("household_free_credit_npl_90d_yoy_change_pp") == {"percentage_points"}
    assert units_for("usd_brl_month_end") == {"brl_per_usd"}
    assert "retail_sales_volume_mom_sa" not in set(analytics.metric_id)


def test_direction_flags_are_descriptive_and_deterministic(analytics: pd.DataFrame) -> None:
    flags = build_macro_direction_flags(analytics)
    values = dict(zip(flags.flag_id, flags.flag_value))
    assert values["selic_direction"] in {"rising", "falling", "unchanged"}
    assert values["inflation_12m_direction"] in {"accelerating", "decelerating", "unchanged"}
    assert values["usd_brl_direction"] == "depreciating_brl"
    assert values["unemployment_direction"] in {"rising", "falling", "unchanged"}
    assert values["credit_yoy_direction"] == "expanding"
    assert values["pix_count_yoy_direction"] == "expanding"
    assert not set(flags.flag_value) & {"good", "bad", "favorable", "unfavorable", "stress", "opportunity"}


@pytest.mark.parametrize(
    ("metric_id", "frequency", "unit", "prior_date", "current_date", "prior", "current", "derived_id", "expected"),
    [
        ("unemployment_rate_rolling_3m", "rolling_3m_monthly", "percent", date(2024, 1, 31), date(2024, 2, 29), 7.0, 8.0, "unemployment_rate_change_pp", "rising"),
        ("unemployment_rate_rolling_3m", "rolling_3m_monthly", "percent", date(2024, 1, 31), date(2024, 2, 29), 8.0, 7.0, "unemployment_rate_change_pp", "falling"),
        ("unemployment_rate_rolling_3m", "rolling_3m_monthly", "percent", date(2024, 1, 31), date(2024, 2, 29), 7.0, 7.0, "unemployment_rate_change_pp", "unchanged"),
        ("household_free_credit_balance", "monthly", "million_brl", date(2023, 2, 28), date(2024, 2, 29), 100.0, 110.0, "household_free_credit_balance_yoy_growth", "expanding"),
        ("household_free_credit_balance", "monthly", "million_brl", date(2023, 2, 28), date(2024, 2, 29), 100.0, 90.0, "household_free_credit_balance_yoy_growth", "contracting"),
        ("household_free_credit_balance", "monthly", "million_brl", date(2023, 2, 28), date(2024, 2, 29), 100.0, 100.0, "household_free_credit_balance_yoy_growth", "unchanged"),
        ("pix_transactions_count_monthly", "monthly", "transactions", date(2023, 2, 28), date(2024, 2, 29), 100.0, 110.0, "pix_transactions_count_yoy_growth", "expanding"),
        ("pix_transactions_count_monthly", "monthly", "transactions", date(2023, 2, 28), date(2024, 2, 29), 100.0, 90.0, "pix_transactions_count_yoy_growth", "contracting"),
        ("pix_transactions_count_monthly", "monthly", "transactions", date(2023, 2, 28), date(2024, 2, 29), 100.0, 100.0, "pix_transactions_count_yoy_growth", "unchanged"),
    ],
)
def test_unemployment_credit_and_pix_direction_states(
    metric_id: str, frequency: str, unit: str, prior_date: date,
    current_date: date, prior: float, current: float, derived_id: str,
    expected: str,
) -> None:
    facts = pd.DataFrame([
        _source_row(metric_id, prior_date, prior, unit, frequency),
        _source_row(metric_id, current_date, current, unit, frequency),
    ])
    row = _one(build_macro_analytics(facts), derived_id, current_date)
    assert row.direction_value == expected


def test_fx_falling_usd_brl_means_appreciating_brl() -> None:
    facts = pd.DataFrame([
        _source_row("usd_brl_sell_rate", date(2023, 12, 29), 5.0, "brl_per_usd", "daily"),
        _source_row("usd_brl_sell_rate", date(2024, 1, 31), 4.8, "brl_per_usd", "daily"),
    ])
    row = _one(build_macro_analytics(facts), "usd_brl_monthly_change_pct", date(2024, 1, 31))
    assert row.direction_value == "appreciating_brl"


def test_macro_observations_are_deterministic_factual_and_non_interpretive(macro_facts: pd.DataFrame, analytics: pd.DataFrame) -> None:
    observations = build_macro_observations(macro_facts, analytics)
    repeated = build_macro_observations(macro_facts, analytics)
    assert observations.evidence_id.tolist() == repeated.evidence_id.tolist()
    assert observations.evidence_id.is_unique
    assert observations.evidence_type.eq("OBSERVATION").all()
    assert observations.business_domain.eq("Macro").all()
    assert observations.is_interpretation.eq(False).all()
    assert observations.claim.str.len().gt(0).all()
    assert observations.source_metric_id.str.len().gt(0).all()
    assert not {"interpretation", "hypothesis", "recommendation", "causal_claim"}.intersection(observations.columns)
    forbidden = ["causou", "explica", "reduz churn", "melhora o mercado pago", "oportunidade", "recomendação", "product"]
    claims = " ".join(observations.claim.str.casefold())
    assert not any(term in claims for term in forbidden)
    sample = observations.loc[observations.metric_id == "pix_transactions_count_yoy_growth"].iloc[0]
    assert "aumentou 25%" in sample.claim
    expected_id = hashlib.sha256(json.dumps({
        "evidence_type": "OBSERVATION", "metric_id": sample.metric_id,
        "reference_date": sample.reference_date.isoformat(), "claim": sample.claim,
        "source_metric_id": sample.source_metric_id,
        "source": sample.source,
        "definition_context": sample.definition_context,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    assert sample.evidence_id == expected_id


def test_pearson_correlation_month_aligns_and_has_known_result() -> None:
    left = pd.DataFrame({"reference_date": [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)], "value": [1, 2, 3]})
    right = pd.DataFrame({"reference_date": [date(2024, 1, 30), date(2024, 2, 28), date(2024, 3, 30)], "value": [2, 4, 6]})
    result = pearson_correlation(left, right, min_observations=3, frequency_a="monthly", frequency_b="monthly")
    assert result["correlation"] == pytest.approx(1.0)
    assert result["n_observations"] == 3
    assert result["start_date"] == date(2024, 1, 31)
    assert result["end_date"] == date(2024, 3, 31)


def test_pearson_correlation_enforces_alignment_minimum_and_constant_series() -> None:
    a = pd.DataFrame({"reference_date": [date(2024, 1, 31), date(2024, 2, 29)], "value": [1, 2]})
    b = pd.DataFrame({"reference_date": [date(2024, 1, 30), date(2024, 2, 28)], "value": [2, 3]})
    with pytest.raises(ValueError, match="Insufficient aligned"):
        pearson_correlation(a, b, min_observations=3, frequency_a="monthly", frequency_b="monthly")
    with pytest.raises(ValueError, match="matching explicit"):
        pearson_correlation(a, b, min_observations=2, frequency_a="daily", frequency_b="monthly")
    constant = b.assign(value=1)
    with pytest.raises(ValueError, match="constant series"):
        pearson_correlation(a, constant, min_observations=2, frequency_a="monthly", frequency_b="monthly")


def test_gold_analytics_roundtrip_replay_conflict_query_and_atomicity(tmp_path: Path, analytics: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "gold" / "macro_analytics.parquet"
    saved_path, metadata_path = write_macro_analytics(analytics, path=path)
    assert saved_path.exists() and metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["dataset"] == "macro_analytics"
    restored = read_macro_analytics(path)
    assert restored.metric_id.tolist() == analytics.metric_id.tolist()
    queried = query_macro_analytics(path=path, metric_id="selic_target_change_pp", start_date=date(2024, 1, 1), end_date=date(2024, 1, 31))
    assert len(queried) == 2
    replay = analytics.copy()
    replay["definition_context"] = "new replay context"
    write_macro_analytics(replay, path=path)
    assert read_macro_analytics(path).iloc[0].definition_context == analytics.iloc[0].definition_context
    conflict = analytics.copy()
    conflict.loc[0, "value"] += 0.25
    with pytest.raises(ValueError, match="revision conflict"):
        write_macro_analytics(conflict, path=path)
    original_bytes = path.read_bytes()
    monkeypatch.setattr(storage.pq, "write_table", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("write failed")))
    with pytest.raises(RuntimeError, match="write failed"):
        write_macro_analytics(analytics, path=path)
    assert path.read_bytes() == original_bytes


def test_gold_evidence_roundtrip_and_deterministic_identity(tmp_path: Path, macro_facts: pd.DataFrame, analytics: pd.DataFrame) -> None:
    observations = build_macro_observations(macro_facts, analytics)
    path = tmp_path / "gold" / "macro_evidence.parquet"
    saved_path, metadata_path = write_macro_evidence(observations, path=path)
    assert saved_path.exists() and metadata_path.exists()
    restored = read_macro_evidence(path)
    assert restored.evidence_id.tolist() == observations.evidence_id.tolist()
    assert restored.evidence_id.is_unique
    replay = write_macro_evidence(observations, path=path)
    assert replay[0].exists()
    queried = query_macro_evidence(path=path, metric_id="pix_transactions_count_yoy_growth", start_date=date(2024, 2, 1), end_date=date(2024, 2, 29))
    assert len(queried) == 1
