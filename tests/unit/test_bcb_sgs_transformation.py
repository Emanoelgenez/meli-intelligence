"""Offline tests for BCB SGS normalization."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from meli_intelligence.transformations.bcb_sgs import normalize_sgs_payload
from meli_intelligence.metadata.bcb_series import BCB_SERIES, get_bcb_series


def _normalize(records: list[dict]) -> pd.DataFrame:
    return normalize_sgs_payload(
        records,
        1178,
        source_url="https://api.bcb.gov.br/example",
        retrieved_at="2026-10-05T00:00:00+00:00",
    )


def test_sgs_payload_normalizes_and_sorts() -> None:
    result = _normalize([
        {"data": "02/01/2023", "valor": "13.65"},
        {"data": "01/01/2023", "valor": "13.65"},
    ])
    assert result["reference_date"].tolist() == [
        pd.Timestamp("2023-01-01").date(),
        pd.Timestamp("2023-01-02").date(),
    ]
    assert result["value"].tolist() == [13.65, 13.65]
    assert set(result["metric_id"]) == {"selic_effective_annual_252"}
    assert set(result["unit"]) == {"percent_per_year"}


@pytest.mark.parametrize(
    ("field", "invalid"),
    [("data", "31/02/2023"), ("valor", "not-a-number")],
)
def test_invalid_sgs_date_or_value_fails(field: str, invalid: str) -> None:
    record = {"data": "01/01/2023", "valor": "13.65"}
    record[field] = invalid
    with pytest.raises(ValueError):
        _normalize([record])


def test_duplicate_economic_key_fails() -> None:
    with pytest.raises(ValueError, match="Duplicate macro economic key"):
        _normalize([
            {"data": "01/01/2023", "valor": "13.65"},
            {"data": "01/01/2023", "valor": "13.65"},
        ])


def test_usd_brl_sgs_registry_and_transformation() -> None:
    assert {1, 432, 1178}.issubset(BCB_SERIES)
    fx = get_bcb_series(1)
    assert fx.metric_id == "usd_brl_sell_rate"
    assert fx.source_series_id == "bcb_sgs:1"
    assert fx.unit == "brl_per_usd"
    assert fx.frequency == "daily"
    assert fx.business_domain == "Macro"
    assert get_bcb_series(432).metric_id == "selic_target_annual"
    assert get_bcb_series(1178).metric_id == "selic_effective_annual_252"

    result = normalize_sgs_payload(
        [{"data": "03/01/2023", "valor": "5.1234"}],
        1,
        source_url="https://api.bcb.gov.br/example/1",
        retrieved_at="2026-10-05T00:00:00+00:00",
    )
    row = result.iloc[0]
    assert row["metric_id"] == "usd_brl_sell_rate"
    assert row["source_series_id"] == "bcb_sgs:1"
    assert row["reference_date"] == pd.Timestamp("2023-01-03").date()
    assert row["value"] == 5.1234
    assert row["unit"] == "brl_per_usd"
    assert row["frequency"] == "daily"
    assert row["source_url"] == "https://api.bcb.gov.br/example/1"
    assert row["retrieved_at"] == "2026-10-05T00:00:00+00:00"
    assert row["ingestion_version"] == "1"


def test_usd_brl_invalid_value_and_duplicate_fail() -> None:
    kwargs = {
        "source_url": "https://api.bcb.gov.br/example/1",
        "retrieved_at": "2026-10-05T00:00:00+00:00",
    }
    with pytest.raises(ValueError):
        normalize_sgs_payload(
            [{"data": "03/01/2023", "valor": "not-a-rate"}], 1, **kwargs
        )
    with pytest.raises(ValueError, match="Duplicate macro economic key"):
        normalize_sgs_payload(
            [
                {"data": "03/01/2023", "valor": "5.1234"},
                {"data": "03/01/2023", "valor": "5.1234"},
            ],
            1,
            **kwargs,
        )


def test_monthly_bcb_series_normalize_to_calendar_month_end() -> None:
    saldo = normalize_sgs_payload(
        [
            {"data": "01/02/2024", "valor": "1922367"},
            {"data": "01/02/2023", "valor": "1800000"},
            {"data": "01/01/2023", "valor": "1750000"},
        ],
        20570,
        source_url="https://api.bcb.gov.br/example/20570",
        retrieved_at="2026-10-05T00:00:00+00:00",
    )
    assert saldo["reference_date"].tolist() == [
        date(2023, 1, 31), date(2023, 2, 28), date(2024, 2, 29),
    ]
    assert saldo["value"].tolist() == [1750000.0, 1800000.0, 1922367.0]
    assert set(saldo["source_series_id"]) == {"bcb_sgs:20570"}
    assert set(saldo["unit"]) == {"million_brl"}
    assert set(saldo["frequency"]) == {"monthly"}

    npl = normalize_sgs_payload(
        [{"data": "01/02/2023", "valor": "4.7"}],
        21112,
        source_url="https://api.bcb.gov.br/example/21112",
        retrieved_at="2026-10-05T00:00:00+00:00",
    )
    assert npl.iloc[0]["reference_date"] == date(2023, 2, 28)
    assert npl.iloc[0]["metric_id"] == "household_free_credit_npl_90d_rate"
    assert npl.iloc[0]["value"] == 4.7
    assert npl.iloc[0]["unit"] == "percent"


def test_month_end_collision_fails_and_daily_bcb_dates_are_unchanged() -> None:
    with pytest.raises(ValueError, match="Duplicate macro economic key"):
        normalize_sgs_payload(
            [
                {"data": "01/01/2023", "valor": "100"},
                {"data": "31/01/2023", "valor": "101"},
            ],
            20570,
            source_url="https://api.bcb.gov.br/example/20570",
            retrieved_at="2026-10-05T00:00:00+00:00",
        )

    for series_code in (1, 432, 1178):
        daily = normalize_sgs_payload(
            [{"data": "01/02/2024", "valor": "5.0"}],
            series_code,
            source_url="https://api.bcb.gov.br/example",
            retrieved_at="2026-10-05T00:00:00+00:00",
        )
        assert daily.iloc[0]["reference_date"] == date(2024, 2, 1)


def test_credit_registry_semantics_and_existing_series() -> None:
    assert {1, 432, 1178, 20570, 21112}.issubset(BCB_SERIES)
    balance = get_bcb_series(20570)
    assert balance.metric_id == "household_free_credit_balance"
    assert balance.source_series_id == "bcb_sgs:20570"
    assert balance.unit == "million_brl"
    assert balance.frequency == "monthly"
    assert balance.business_domain == "Macro"

    npl = get_bcb_series(21112)
    assert npl.metric_id == "household_free_credit_npl_90d_rate"
    assert npl.source_series_id == "bcb_sgs:21112"
    assert npl.unit == "percent"
    assert npl.frequency == "monthly"
    assert npl.business_domain == "Macro"

    assert get_bcb_series(432).metric_id == "selic_target_annual"
    assert get_bcb_series(1178).metric_id == "selic_effective_annual_252"
    assert get_bcb_series(1).metric_id == "usd_brl_sell_rate"


def test_ibc_br_registry_and_monthly_normalization() -> None:
    activity = get_bcb_series(24364)
    assert activity.metric_id == "ibc_br_activity_sa_index"
    assert activity.source_series_id == "bcb_sgs:24364"
    assert activity.unit == "index"
    assert activity.frequency == "monthly"
    assert activity.business_domain == "Macro"
    normalized = normalize_sgs_payload(
        [{"data": "01/02/2024", "valor": "151.2"}], 24364,
        source_url="https://bcb", retrieved_at="now",
    )
    assert normalized.iloc[0]["reference_date"] == date(2024, 2, 29)
    assert normalized.iloc[0]["value"] == 151.2
