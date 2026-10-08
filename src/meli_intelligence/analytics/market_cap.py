"""Historical MELI market capitalization from exact market and SEC inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Any, Iterable

import pandas as pd

ENTITY = "MercadoLibre, Inc."
TICKER = "MELI"
SEC_SOURCE = "SEC EDGAR Company Facts API"
SEC_SOURCE_LABELS = frozenset({
    SEC_SOURCE,
    "SEC Company Facts",
})
SEC_TAXONOMY = "dei"
SEC_CONCEPT = "EntityCommonStockSharesOutstanding"
SEC_METRIC_ID = f"{SEC_TAXONOMY}:{SEC_CONCEPT}"

STATUS_AVAILABLE = "AVAILABLE"
STATUS_MISSING_SHARE_COUNT = "UNAVAILABLE_MISSING_SHARE_COUNT"
STATUS_LOOKAHEAD = "UNAVAILABLE_LOOKAHEAD"
STATUS_INVALID_PRICE = "UNAVAILABLE_INVALID_PRICE"
STATUS_INVALID_SHARE_COUNT = "UNAVAILABLE_INVALID_SHARE_COUNT"
STATUS_CURRENCY_MISMATCH = "UNAVAILABLE_CURRENCY_MISMATCH"
STATUS_UNSUPPORTED_TICKER = "UNAVAILABLE_UNSUPPORTED_TICKER"
MARKET_CAP_STATUSES = frozenset({
    STATUS_AVAILABLE,
    STATUS_MISSING_SHARE_COUNT,
    STATUS_LOOKAHEAD,
    STATUS_INVALID_PRICE,
    STATUS_INVALID_SHARE_COUNT,
    STATUS_CURRENCY_MISMATCH,
    STATUS_UNSUPPORTED_TICKER,
})


@dataclass(frozen=True)
class SharesOutstandingFact:
    entity: str
    value: float
    reference_date: date
    filed_at: date
    accession_number: str
    source: str
    source_metric_id: str
    unit: str = "shares"
    taxonomy: str = SEC_TAXONOMY
    concept: str = SEC_CONCEPT
    form: str = "10-K"
    source_url: str = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001099590.json"


@dataclass(frozen=True)
class MarketCapitalization:
    value: float | None
    currency: str
    reference_date: date | None
    status: str
    reason: str | None
    price: float | None
    shares_outstanding: float | None
    source_metric_ids: tuple[str, ...]
    shares_reference_date: date | None = None
    shares_filed_at: date | None = None
    shares_accession_number: str | None = None
    shares_source: str | None = None
    shares_source_url: str | None = None


def _as_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _coerce_fact(row: SharesOutstandingFact | dict[str, Any]) -> SharesOutstandingFact | None:
    if isinstance(row, SharesOutstandingFact):
        return row
    if not isinstance(row, dict):
        return None
    try:
        return SharesOutstandingFact(
            entity=str(row["entity"]),
            value=float(row["value"]),
            reference_date=_as_date(row["reference_date"]),
            filed_at=_as_date(row["filed_at"]),
            accession_number=str(row["accession_number"]),
            source=str(row["source"]),
            source_metric_id=str(row.get("source_metric_id", "")),
            unit=str(row["unit"]),
            taxonomy=str(row["taxonomy"]),
            concept=str(row["concept"]),
            form=str(row["form"]),
            source_url=str(row["source_url"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _facts(facts: pd.DataFrame | Iterable[SharesOutstandingFact | dict[str, Any]] | None) -> list[SharesOutstandingFact]:
    if facts is None:
        return []
    records = facts.to_dict("records") if isinstance(facts, pd.DataFrame) else list(facts)
    normalized = []
    for row in records:
        fact = _coerce_fact(row)
        if fact is not None:
            normalized.append(fact)
    return normalized


def _is_authoritative(fact: SharesOutstandingFact) -> bool:
    return (
        fact.entity == ENTITY
        and isinstance(fact.reference_date, date)
        and isinstance(fact.filed_at, date)
        and fact.source in SEC_SOURCE_LABELS
        and fact.taxonomy == SEC_TAXONOMY
        and fact.concept == SEC_CONCEPT
        and fact.source_metric_id == SEC_METRIC_ID
        and fact.unit.casefold() == "shares"
        and fact.form in {"10-K", "10-Q"}
        and bool(fact.accession_number.strip())
        and bool(fact.source_url.startswith("https://data.sec.gov/api/xbrl/companyfacts/"))
    )


def select_shares_outstanding_as_of(
    facts: pd.DataFrame | Iterable[SharesOutstandingFact | dict[str, Any]] | None,
    *,
    market_reference_date: date,
) -> SharesOutstandingFact | None:
    """Select the latest eligible SEC share-count fact, with no look-ahead.

    Ordering is economic reference date descending, filing date descending,
    then accession number descending, matching the SEC normalizer's stable
    latest-filing tie-break for a duplicate economic context.
    """
    candidates = [fact for fact in _facts(facts) if _is_authoritative(fact)]
    eligible = [
        fact for fact in candidates
        if fact.reference_date <= market_reference_date
        and fact.filed_at <= market_reference_date
        and math.isfinite(fact.value)
        and fact.value > 0
    ]
    if not eligible:
        return None
    eligible.sort(
        key=lambda fact: (fact.reference_date, fact.filed_at, fact.accession_number),
        reverse=True,
    )
    first = eligible[0]
    tied = [
        fact for fact in eligible
        if (fact.reference_date, fact.filed_at, fact.accession_number)
        == (first.reference_date, first.filed_at, first.accession_number)
    ]
    if len({fact.value for fact in tied}) > 1:
        return None
    return first


def calculate_market_cap(
    *,
    ticker: str,
    price: float | None,
    currency: str | None,
    market_reference_date: date,
    shares_facts: pd.DataFrame | Iterable[SharesOutstandingFact | dict[str, Any]] | None,
) -> MarketCapitalization:
    """Multiply an exact MELI USD close by the latest eligible SEC share fact."""
    def unavailable(status: str, reason: str, *, shares: float | None = None) -> MarketCapitalization:
        return MarketCapitalization(None, currency or "USD", market_reference_date, status, reason, price, shares, ())

    if ticker != TICKER:
        return unavailable(STATUS_UNSUPPORTED_TICKER, "Market capitalization is supported only for MELI.")
    if currency != "USD":
        return unavailable(STATUS_CURRENCY_MISMATCH, "MELI market price must be denominated in USD.")
    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        return unavailable(STATUS_INVALID_PRICE, "Market close must be finite and greater than zero.")
    if not math.isfinite(numeric_price) or numeric_price <= 0:
        return unavailable(STATUS_INVALID_PRICE, "Market close must be finite and greater than zero.")

    facts = _facts(shares_facts)
    authoritative = [fact for fact in facts if _is_authoritative(fact)]
    eligible = [
        fact for fact in authoritative
        if fact.reference_date <= market_reference_date and fact.filed_at <= market_reference_date
    ]
    if not eligible:
        if authoritative and any(fact.reference_date <= market_reference_date for fact in authoritative):
            return unavailable(STATUS_LOOKAHEAD, "No eligible shares fact was filed by the Market reference date.")
        return unavailable(STATUS_MISSING_SHARE_COUNT, "No authoritative SEC shares-outstanding fact is available.")
    selected = select_shares_outstanding_as_of(eligible, market_reference_date=market_reference_date)
    if selected is None:
        return unavailable(STATUS_INVALID_SHARE_COUNT, "Eligible SEC shares-outstanding facts are invalid or conflicting.")
    if not math.isfinite(selected.value) or selected.value <= 0:
        return unavailable(STATUS_INVALID_SHARE_COUNT, "SEC shares outstanding must be finite and greater than zero.")
    return MarketCapitalization(
        value=numeric_price * selected.value,
        currency="USD",
        reference_date=market_reference_date,
        status=STATUS_AVAILABLE,
        reason=None,
        price=numeric_price,
        shares_outstanding=selected.value,
        source_metric_ids=("market:close", selected.source_metric_id),
        shares_reference_date=selected.reference_date,
        shares_filed_at=selected.filed_at,
        shares_accession_number=selected.accession_number,
        shares_source=selected.source,
        shares_source_url=selected.source_url,
    )


MARKET_CAP_GOLD_COLUMNS = (
    "ticker", "entity", "reference_date", "value", "currency", "status", "reason",
    "price", "shares_outstanding", "shares_reference_date", "shares_filed_at",
    "shares_accession_number", "source_metric_ids", "market_source", "market_source_url",
    "market_retrieved_at", "market_source_bronze_file", "market_source_content_sha256",
    "shares_source", "shares_source_url", "methodology_version",
)
MARKET_CAP_METHODOLOGY_VERSION = "1"


def build_market_cap_gold(
    market_prices: pd.DataFrame | None,
    shares_facts: pd.DataFrame | Iterable[SharesOutstandingFact | dict[str, Any]] | None,
) -> pd.DataFrame:
    """Build one derived Gold market-cap row per exact persisted Market observation.

    The helper never resamples or fills Market dates. Each result uses the
    existing as-of share selector and calculation contract.
    """
    if market_prices is None or market_prices.empty:
        return pd.DataFrame(columns=list(MARKET_CAP_GOLD_COLUMNS))
    required = {"ticker", "entity", "reference_date", "close", "currency", "source", "source_url", "retrieved_at"}
    missing = required.difference(market_prices.columns)
    if missing:
        raise ValueError(f"Market prices are missing columns: {sorted(missing)}")
    frame = market_prices.copy(deep=True)
    frame["reference_date"] = frame.reference_date.map(_as_date)
    if frame.reference_date.isna().any():
        raise ValueError("Market prices contain invalid reference_date values.")
    if frame.duplicated(["ticker", "reference_date"], keep=False).any():
        raise ValueError("Market prices contain duplicate ticker + reference_date observations.")
    frame = frame.sort_values(["ticker", "reference_date"], kind="mergesort")
    records: list[dict[str, Any]] = []
    for market in frame.to_dict("records"):
        reference_date = market["reference_date"]
        result = calculate_market_cap(
            ticker=str(market["ticker"]),
            price=market["close"],
            currency=str(market["currency"]),
            market_reference_date=reference_date,
            shares_facts=shares_facts,
        )
        records.append({
            "ticker": str(market["ticker"]),
            "entity": str(market["entity"]),
            "reference_date": reference_date,
            "value": result.value,
            "currency": result.currency,
            "status": result.status,
            "reason": result.reason,
            "price": result.price,
            "shares_outstanding": result.shares_outstanding,
            "shares_reference_date": result.shares_reference_date,
            "shares_filed_at": result.shares_filed_at,
            "shares_accession_number": result.shares_accession_number,
            "source_metric_ids": ";".join(result.source_metric_ids),
            "market_source": str(market["source"]),
            "market_source_url": str(market["source_url"]),
            "market_retrieved_at": str(market["retrieved_at"]),
            "market_source_bronze_file": market.get("source_bronze_file"),
            "market_source_content_sha256": market.get("source_content_sha256"),
            "shares_source": result.shares_source,
            "shares_source_url": result.shares_source_url,
            "methodology_version": MARKET_CAP_METHODOLOGY_VERSION,
        })
    return pd.DataFrame(records, columns=list(MARKET_CAP_GOLD_COLUMNS))
