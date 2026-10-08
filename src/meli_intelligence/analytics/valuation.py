"""Conservative historical valuation availability and filing-safe fact alignment."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import pandas as pd

from meli_intelligence.analytics.market_cap import (
    MarketCapitalization,
    STATUS_AVAILABLE as MARKET_CAP_AVAILABLE,
)

STATUS_AVAILABLE = "AVAILABLE"
STATUS_MISSING_MARKET_CAP = "UNAVAILABLE_MISSING_MARKET_CAP"
STATUS_NO_ELIGIBLE_MARKET_CAP = "UNAVAILABLE_NO_ELIGIBLE_MARKET_CAP"
STATUS_GOLD_MARKET_CAP_UNAVAILABLE = "UNAVAILABLE_GOLD_MARKET_CAP"
STATUS_INVALID_MARKET_CAP = "UNAVAILABLE_INVALID_MARKET_CAP"
STATUS_CURRENCY_MISMATCH = "UNAVAILABLE_CURRENCY_MISMATCH"
STATUS_UNSUPPORTED_TICKER = "UNAVAILABLE_UNSUPPORTED_TICKER"
STATUS_MISSING_DENOMINATOR = "UNAVAILABLE_MISSING_DENOMINATOR"
STATUS_INVALID_DENOMINATOR = "UNAVAILABLE_INVALID_DENOMINATOR"
STATUS_LOOKAHEAD_PREVENTED = "UNAVAILABLE_LOOKAHEAD_PREVENTED"
STATUS_PERIOD_MISMATCH = "UNAVAILABLE_PERIOD_MISMATCH"
VALUATION_STATUSES = frozenset({
    STATUS_AVAILABLE,
    STATUS_MISSING_MARKET_CAP,
    STATUS_NO_ELIGIBLE_MARKET_CAP,
    STATUS_GOLD_MARKET_CAP_UNAVAILABLE,
    STATUS_INVALID_MARKET_CAP,
    STATUS_CURRENCY_MISMATCH,
    STATUS_UNSUPPORTED_TICKER,
    STATUS_MISSING_DENOMINATOR,
    STATUS_INVALID_DENOMINATOR,
    STATUS_LOOKAHEAD_PREVENTED,
    STATUS_PERIOD_MISMATCH,
})


@dataclass(frozen=True)
class ValuationMetric:
    metric_id: str
    label: str
    value: float | None
    unit: str
    reference_date: date | None
    status: str
    reason: str | None
    source_metric_ids: tuple[str, ...]
    source_accession_numbers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinancialFactAsOf:
    """A canonical financial fact that was public by the market date."""

    metric_id: str
    value: float
    unit: str
    period_start: date | None
    period_end: date
    period_type: str
    filed_at: date
    accession_number: str


@dataclass(frozen=True)
class MarketCapGoldSelection:
    """The latest eligible persisted Gold row, without recomputing its value."""

    ticker: str | None
    value: float | None
    currency: str
    reference_date: date | None
    status: str
    gold_status: str | None
    reason: str | None
    price: float | None
    shares_outstanding: float | None
    shares_reference_date: date | None
    shares_filed_at: date | None
    shares_accession_number: str | None
    source_metric_ids: tuple[str, ...]
    methodology_version: str | None
    market_source: str | None
    market_source_url: str | None


@dataclass(frozen=True)
class ValuationSnapshot:
    valuation_reference_date: date
    market_cap: MarketCapGoldSelection
    metrics: tuple[ValuationMetric, ...]


@dataclass(frozen=True)
class _MetricSpec:
    metric_id: str
    label: str
    denominator_metric_id: str
    expected_period_type: str


_METRICS = (
    _MetricSpec("price_to_sales", "Price to sales", "net_revenues_financial_income", "QUARTER"),
    _MetricSpec("price_to_book", "Price to book", "stockholders_equity", "INSTANT"),
    _MetricSpec("price_to_operating_cash_flow", "Price to operating cash flow", "operating_cash_flow", "QUARTER"),
)
_FACT_PERIODS = {
    "net_revenues_financial_income": "QUARTER",
    "stockholders_equity": "INSTANT",
    "operating_cash_flow": "QUARTER",
}
_MISSING_CAP_REASON = (
    "Authoritative market capitalization and share-count inputs are absent; "
    "no market capitalization or valuation multiple is estimated."
)


def _to_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _market_cap_lineage(value: object) -> tuple[str, ...]:
    if isinstance(value, (tuple, list)):
        candidates = (str(item).strip() for item in value)
    elif value is None or pd.isna(value):
        candidates = ()
    else:
        candidates = (item.strip() for item in str(value).split(";"))
    return tuple(item for item in candidates if item)


def _gold_selection_unavailable(
    *,
    status: str,
    reason: str,
    ticker: str | None = None,
    currency: str = "USD",
) -> MarketCapGoldSelection:
    return MarketCapGoldSelection(
        ticker=ticker, value=None, currency=currency,
        reference_date=None, status=status, gold_status=None, reason=reason,
        price=None, shares_outstanding=None, shares_reference_date=None,
        shares_filed_at=None, shares_accession_number=None,
        source_metric_ids=(), methodology_version=None,
        market_source=None, market_source_url=None,
    )


def select_market_cap_gold_as_of(
    market_cap_gold: pd.DataFrame | None,
    *,
    valuation_reference_date: date,
) -> MarketCapGoldSelection:
    """Select the latest persisted MELI Gold row not later than the requested date.

    The latest row is selected before availability is checked, so an unavailable
    current Gold observation cannot fall back to an older market capitalization.
    No market value is calculated, interpolated, or forward-filled here.
    """
    if not isinstance(valuation_reference_date, date):
        raise TypeError("valuation_reference_date must be a date.")
    if market_cap_gold is None or market_cap_gold.empty:
        return _gold_selection_unavailable(
            status=STATUS_NO_ELIGIBLE_MARKET_CAP,
            reason="No persisted Market Cap Gold observations are available.",
        )
    required = {
        "ticker", "reference_date", "value", "currency", "status", "reason",
        "price", "shares_outstanding", "shares_reference_date", "shares_filed_at",
        "shares_accession_number", "source_metric_ids", "methodology_version",
        "market_source", "market_source_url",
    }
    missing = required.difference(market_cap_gold.columns)
    if missing:
        raise ValueError(f"Market Cap Gold is missing columns: {sorted(missing)}")
    rows = market_cap_gold.copy(deep=True)
    rows["_reference_date"] = rows.reference_date.map(_to_date)
    rows = rows.loc[rows.ticker.astype(str).eq("MELI")].copy()
    if rows.empty:
        return _gold_selection_unavailable(
            status=STATUS_UNSUPPORTED_TICKER,
            reason="Valuation consumption supports MELI only.",
        )
    if rows._reference_date.isna().any():
        raise ValueError("Market Cap Gold contains an invalid reference_date.")
    if rows.duplicated(["ticker", "_reference_date"], keep=False).any():
        raise ValueError("Market Cap Gold contains duplicate ticker + reference_date rows.")
    eligible = rows.loc[rows._reference_date <= valuation_reference_date]
    if eligible.empty:
        return _gold_selection_unavailable(
            status=STATUS_NO_ELIGIBLE_MARKET_CAP,
            reason="No MELI Market Cap Gold observation exists on or before the valuation reference date.",
            ticker="MELI",
        )
    selected = eligible.sort_values("_reference_date", ascending=False, kind="mergesort").iloc[0]
    selected_date = selected["_reference_date"]
    ticker = str(selected.ticker)
    currency = str(selected.currency)
    gold_status = str(selected.status)
    source_ids = _market_cap_lineage(selected.source_metric_ids)
    shares_reference_date = _to_date(selected.shares_reference_date)
    shares_filed_at = _to_date(selected.shares_filed_at)
    reason_value = selected.reason
    reason = None if reason_value is None or pd.isna(reason_value) else str(reason_value)
    status = gold_status
    value: float | None = None
    if currency != "USD":
        status = STATUS_CURRENCY_MISMATCH
        reason = "Persisted MELI Market Cap Gold must be denominated in USD."
    elif gold_status != MARKET_CAP_AVAILABLE:
        status = STATUS_GOLD_MARKET_CAP_UNAVAILABLE
        reason = reason or f"Selected Market Cap Gold row is unavailable ({gold_status})."
    else:
        try:
            candidate_value = float(selected.value)
        except (TypeError, ValueError):
            candidate_value = math.nan
        if not math.isfinite(candidate_value) or candidate_value <= 0:
            status = STATUS_INVALID_MARKET_CAP
            reason = "Selected AVAILABLE Gold row does not contain a finite positive market-cap value."
        elif shares_reference_date is None or shares_filed_at is None:
            status = STATUS_INVALID_MARKET_CAP
            reason = "Selected AVAILABLE Gold row is missing authoritative share-count dates."
        elif shares_reference_date > selected_date or shares_filed_at > selected_date:
            status = STATUS_LOOKAHEAD_PREVENTED
            reason = "Selected Gold row contains a share-count fact not eligible as of its Market reference date."
        else:
            value = candidate_value
            status = STATUS_AVAILABLE
            reason = None

    def numeric_or_none(column: str) -> float | None:
        try:
            number = float(selected[column])
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    return MarketCapGoldSelection(
        ticker=ticker,
        value=value,
        currency=currency,
        reference_date=selected_date,
        status=status,
        gold_status=gold_status,
        reason=reason,
        price=numeric_or_none("price"),
        shares_outstanding=numeric_or_none("shares_outstanding"),
        shares_reference_date=shares_reference_date,
        shares_filed_at=shares_filed_at,
        shares_accession_number=(
            None if pd.isna(selected.shares_accession_number)
            else str(selected.shares_accession_number)
        ),
        source_metric_ids=source_ids,
        methodology_version=(
            None if pd.isna(selected.methodology_version)
            else str(selected.methodology_version)
        ),
        market_source=(None if pd.isna(selected.market_source) else str(selected.market_source)),
        market_source_url=(None if pd.isna(selected.market_source_url) else str(selected.market_source_url)),
    )


def build_valuation_snapshot(
    market_cap_gold: pd.DataFrame | None,
    financial_facts: pd.DataFrame | None,
    *,
    valuation_reference_date: date,
) -> ValuationSnapshot:
    """Consume persisted Market Cap Gold and Company facts as of one date."""
    selection = select_market_cap_gold_as_of(
        market_cap_gold, valuation_reference_date=valuation_reference_date,
    )
    selected_cap = MarketCapitalization(
        value=selection.value,
        currency=selection.currency,
        reference_date=selection.reference_date,
        status=MARKET_CAP_AVAILABLE if selection.status == STATUS_AVAILABLE else selection.status,
        reason=selection.reason,
        price=selection.price,
        shares_outstanding=selection.shares_outstanding,
        source_metric_ids=selection.source_metric_ids,
        shares_reference_date=selection.shares_reference_date,
        shares_filed_at=selection.shares_filed_at,
        shares_accession_number=selection.shares_accession_number,
    )
    metrics = build_valuation_availability(
        market_reference_date=valuation_reference_date,
        market_cap=selected_cap,
        financial_facts=financial_facts,
    )
    return ValuationSnapshot(
        valuation_reference_date=valuation_reference_date,
        market_cap=selection,
        metrics=metrics,
    )


def build_valuation_availability(
    *,
    market_reference_date: date | None = None,
    market_cap: MarketCapitalization | None = None,
    financial_facts: pd.DataFrame | None = None,
) -> tuple[ValuationMetric, ...]:
    """Return deterministic candidate states, using only compatible inputs.

    Price-to-book is supported from eligible instant equity. Price-to-sales
    and price-to-operating-cash-flow remain unavailable because quarterly
    duration facts are not a trailing-twelve-month denominator.
    """
    reference_date = _to_date(market_reference_date or (market_cap.reference_date if market_cap else None))
    if (
        market_cap is None
        or market_cap.status != MARKET_CAP_AVAILABLE
        or market_cap.value is None
        or market_cap.reference_date is None
        or not math.isfinite(market_cap.value)
        or market_cap.value <= 0
    ):
        missing_reason = _MISSING_CAP_REASON
        if market_cap is not None and market_cap.reason:
            missing_reason = (
                f"Persisted market capitalization is unavailable ({market_cap.status}): "
                f"{market_cap.reason}"
            )
        return tuple(
            ValuationMetric(
                metric_id=spec.metric_id, label=spec.label, value=None, unit="multiple",
                reference_date=reference_date, status=STATUS_MISSING_MARKET_CAP,
                reason=missing_reason,
                source_metric_ids=market_cap.source_metric_ids if market_cap else (),
            )
            for spec in _METRICS
        )
    if market_cap.currency != "USD" or (reference_date and market_cap.reference_date > reference_date):
        return tuple(
            ValuationMetric(
                metric_id=spec.metric_id, label=spec.label, value=None, unit="multiple",
                reference_date=reference_date, status=STATUS_PERIOD_MISMATCH,
                reason="Market capitalization currency or reference date is incompatible with the requested valuation date.",
                source_metric_ids=market_cap.source_metric_ids,
            )
            for spec in _METRICS
        )

    outputs: list[ValuationMetric] = []
    for spec in _METRICS:
        lineage = market_cap.source_metric_ids
        if spec.metric_id == "price_to_book":
            denominator = select_financial_fact_as_of(
                financial_facts,
                metric_id=spec.denominator_metric_id,
                market_reference_date=reference_date or market_cap.reference_date,
            )
            if denominator is None or denominator.value <= 0:
                unavailable_status, unavailable_reason = _financial_fact_unavailability(
                    financial_facts,
                    metric_id=spec.denominator_metric_id,
                    market_reference_date=reference_date or market_cap.reference_date,
                    expected_period_type=spec.expected_period_type,
                )
                outputs.append(ValuationMetric(
                    spec.metric_id, spec.label, None, "multiple", reference_date or market_cap.reference_date,
                    unavailable_status,
                    unavailable_reason,
                    lineage,
                ))
            else:
                outputs.append(ValuationMetric(
                    spec.metric_id, spec.label, market_cap.value / denominator.value,
                    "multiple", reference_date or market_cap.reference_date, STATUS_AVAILABLE, None,
                    tuple(sorted(set((*lineage, denominator.metric_id)))),
                    tuple(sorted({
                        accession for accession in (
                            market_cap.shares_accession_number,
                            denominator.accession_number,
                        ) if accession
                    })),
                ))
            continue
        quarter_fact = select_financial_fact_as_of(
            financial_facts,
            metric_id=spec.denominator_metric_id,
            market_reference_date=reference_date or market_cap.reference_date,
        )
        if quarter_fact is None:
            unavailable_status, unavailable_reason = _financial_fact_unavailability(
                financial_facts,
                metric_id=spec.denominator_metric_id,
                market_reference_date=reference_date or market_cap.reference_date,
                expected_period_type=spec.expected_period_type,
            )
            outputs.append(ValuationMetric(
                spec.metric_id, spec.label, None, "multiple", reference_date or market_cap.reference_date,
                unavailable_status,
                unavailable_reason,
                lineage,
            ))
            continue
        outputs.append(ValuationMetric(
            spec.metric_id, spec.label, None, "multiple", reference_date or market_cap.reference_date,
            STATUS_PERIOD_MISMATCH,
            "A compatible annual or trailing-twelve-month duration denominator is not available; a quarter alone is insufficient.",
            tuple(sorted(set((*lineage, quarter_fact.metric_id)))),
            (quarter_fact.accession_number,) if quarter_fact.accession_number else (),
        ))
    return tuple(outputs)


def select_financial_fact_as_of(
    financial_facts: pd.DataFrame | None,
    *,
    metric_id: str,
    market_reference_date: date,
) -> FinancialFactAsOf | None:
    """Select a defensible period fact filed no later than a market date.

    Duration denominators accept canonical QUARTER only. Stockholders' equity
    accepts INSTANT only. YTD/FY flows and duration/instant substitutions do
    not align for these V1 candidates and return None.
    """
    expected_period = _FACT_PERIODS.get(metric_id)
    if expected_period is None:
        raise ValueError(f"Unsupported valuation input metric_id: {metric_id!r}.")
    if not isinstance(market_reference_date, date):
        raise TypeError("market_reference_date must be a date.")
    if financial_facts is None or financial_facts.empty:
        return None
    required = {
        "metric_id", "value", "unit", "period_start", "period_end",
        "period_type", "filed_at", "accession_number",
    }
    if not required.issubset(financial_facts.columns):
        return None

    rows = financial_facts.loc[financial_facts.metric_id.astype(str).eq(metric_id)].copy()
    if rows.empty:
        return None
    rows["_period_type"] = rows.period_type.astype(str).str.upper()
    rows = rows.loc[rows._period_type.eq(expected_period)].copy()
    if rows.empty:
        return None
    rows["_period_end"] = rows.period_end.map(_to_date)
    rows["_period_start"] = rows.period_start.map(_to_date)
    rows["_filed_at"] = rows.filed_at.map(_to_date)
    rows["_value"] = pd.to_numeric(rows.value, errors="coerce")
    valid = rows._period_end.notna() & rows._filed_at.notna()
    valid &= rows._period_end.map(lambda value: value <= market_reference_date if value else False)
    valid &= rows._filed_at.map(lambda value: value <= market_reference_date if value else False)
    valid &= rows._value.map(lambda value: pd.notna(value) and math.isfinite(float(value)))
    valid &= rows.unit.astype(str).eq("USD")
    if expected_period == "INSTANT":
        valid &= rows._period_start.isna()
    else:
        valid &= rows._period_start.notna()
        valid &= rows.apply(
            lambda row: row["_period_start"] <= row["_period_end"]
            if row["_period_start"] is not None and row["_period_end"] is not None else False,
            axis=1,
        )
    if "is_derived" in rows.columns:
        valid &= ~rows.is_derived.fillna(True).astype(bool)
    rows = rows.loc[valid].copy()
    if rows.empty:
        return None

    rows["_accession"] = rows.accession_number.fillna("").astype(str)
    rows = rows.sort_values(
        ["_period_end", "_filed_at", "_accession"],
        ascending=[False, False, True], kind="mergesort",
    )
    selected = rows.iloc[0]
    # Do not choose arbitrarily if two filings tie on the latest economic
    # period and filed date but report conflicting values.
    tied = rows.loc[
        rows._period_end.eq(selected._period_end)
        & rows._filed_at.eq(selected._filed_at)
    ]
    if tied._value.nunique(dropna=False) > 1:
        return None
    return FinancialFactAsOf(
        metric_id=metric_id,
        value=float(selected._value),
        unit=str(selected.unit),
        period_start=selected._period_start,
        period_end=selected._period_end,
        period_type=expected_period,
        filed_at=selected._filed_at,
        accession_number=str(selected._accession),
    )


def _financial_fact_unavailability(
    financial_facts: pd.DataFrame | None,
    *,
    metric_id: str,
    market_reference_date: date,
    expected_period_type: str,
) -> tuple[str, str]:
    """Explain a failed selection without changing the selector's eligibility rules."""
    if financial_facts is None or financial_facts.empty:
        return STATUS_MISSING_DENOMINATOR, "No eligible denominator fact is present."
    required = {"metric_id", "unit", "period_type", "period_start", "period_end", "filed_at", "value"}
    if not required.issubset(financial_facts.columns):
        return STATUS_MISSING_DENOMINATOR, "Financial facts do not contain the fields needed for denominator eligibility."
    candidates = financial_facts.loc[
        financial_facts.metric_id.astype(str).eq(metric_id)
        & financial_facts.period_type.astype(str).str.upper().eq(expected_period_type)
        & financial_facts.unit.astype(str).eq("USD")
    ].copy()
    if candidates.empty:
        return STATUS_MISSING_DENOMINATOR, "No compatible financial denominator fact is present."
    candidates["_period_end"] = candidates.period_end.map(_to_date)
    candidates["_period_start"] = candidates.period_start.map(_to_date)
    candidates["_filed_at"] = candidates.filed_at.map(_to_date)
    candidates = candidates.loc[
        candidates._period_end.notna()
        & candidates._period_end.map(lambda value: value <= market_reference_date)
    ]
    if expected_period_type == "INSTANT":
        candidates = candidates.loc[candidates._period_start.isna()]
    else:
        candidates = candidates.loc[
            candidates._period_start.notna()
            & candidates.apply(
                lambda row: row["_period_start"] <= row["_period_end"]
                if row["_period_start"] is not None and row["_period_end"] is not None else False,
                axis=1,
            )
        ]
    if "is_derived" in candidates.columns:
        candidates = candidates.loc[~candidates.is_derived.fillna(True).astype(bool)]
    if candidates.empty:
        return STATUS_MISSING_DENOMINATOR, "No compatible denominator fact is available for a period ending by the valuation date."
    filed = candidates._filed_at
    if filed.map(lambda value: value is not None and value > market_reference_date).any():
        return STATUS_LOOKAHEAD_PREVENTED, "A candidate financial fact was withheld because its filing date is after the valuation reference date."
    if filed.isna().any():
        return STATUS_MISSING_DENOMINATOR, "A candidate financial fact has no usable filing date."
    values = pd.to_numeric(candidates.value, errors="coerce")
    if values.isna().any() or not values.map(lambda value: math.isfinite(float(value))).all() or (values <= 0).any():
        return STATUS_INVALID_DENOMINATOR, "The eligible financial denominator is not finite and positive."
    return STATUS_MISSING_DENOMINATOR, "No unambiguous eligible denominator fact is available."
