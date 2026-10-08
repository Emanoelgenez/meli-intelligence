"""Safe operational orchestration for Twelve Data Bronze to Market Silver."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from meli_intelligence.sources.market.twelve_data import (
    DEFAULT_OUTPUTSIZE,
    ENDPOINT,
    INTERVAL,
    TICKER,
    PROVIDER,
    TwelveDataClient,
    build_request_params,
)
from meli_intelligence.storage.market_bronze import DEFAULT_MARKET_BRONZE_DIR, save_market_bronze
from meli_intelligence.storage.market_prices import (
    DEFAULT_MARKET_PRICES_PATH, merge_market_prices, read_market_prices, write_market_prices,
)
from meli_intelligence.transformations.market_prices import normalize_market_prices

MARKET_EXCHANGE_TIMEZONE = "America/New_York"
MARKET_TIMEZONE = ZoneInfo(MARKET_EXCHANGE_TIMEZONE)


@dataclass(frozen=True)
class MarketIngestionPlan:
    source: str
    ticker: str
    interval: str
    start_date: date | None
    end_date: date
    safe_boundary_date: date
    outputsize: int
    timezone: str
    endpoint: str


@dataclass(frozen=True)
class MarketPricePipelineSummary:
    source: str
    ticker: str
    rows_received: int
    rows_written: int
    earliest_reference_date: str
    latest_reference_date: str
    bronze_path: str
    silver_path: str
    content_sha256: str
    requested_start_date: str | None = None
    requested_end_date: str | None = None
    safe_boundary_date: str | None = None


def _as_date(value: date | str | None, name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise TypeError(f"{name} must be a date, not datetime.")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD).") from None


def resolve_completed_session_boundary(*, now: datetime | None = None) -> date:
    """Resolve today's civil date in New York; reject naive clock values."""
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    return instant.astimezone(MARKET_TIMEZONE).date()


def build_market_ingestion_plan(
    *, start_date: date | str | None = None,
    end_date: date | str | None = None,
    outputsize: int = DEFAULT_OUTPUTSIZE,
    now: datetime | None = None,
) -> MarketIngestionPlan:
    """Build a validated, network-free and filesystem-free ingestion plan."""
    boundary = resolve_completed_session_boundary(now=now)
    start = _as_date(start_date, "start_date")
    requested_end = _as_date(end_date, "end_date") if end_date is not None else boundary
    if requested_end > boundary:
        raise ValueError("end_date cannot be later than the current America/New_York boundary.")
    if start is not None and start > requested_end:
        raise ValueError("start_date must be on or before the resolved end_date.")
    # Reuse the source client's validation without placing credentials in this plan.
    params = build_request_params(start_date=start, end_date=requested_end, outputsize=outputsize)
    del params
    return MarketIngestionPlan(
        source=PROVIDER, ticker=TICKER, interval=INTERVAL, start_date=start,
        end_date=requested_end, safe_boundary_date=boundary, outputsize=outputsize,
        timezone=MARKET_EXCHANGE_TIMEZONE, endpoint=ENDPOINT,
    )


def format_market_ingestion_plan(plan: MarketIngestionPlan) -> str:
    return "\n".join((
        f"Provider: {plan.source}", f"Ticker: {plan.ticker}", f"Interval: {plan.interval}",
        f"Exchange timezone: {plan.timezone}", f"Safe boundary: {plan.safe_boundary_date.isoformat()}",
        f"Start date: {plan.start_date.isoformat() if plan.start_date else '<none>'}",
        f"End boundary: {plan.end_date.isoformat()}", f"Output size: {plan.outputsize}",
        f"Endpoint: {plan.endpoint}", "Network: disabled (dry-run)", "Writes: disabled (dry-run)",
    ))


def run_market_price_pipeline(
    *, start_date: date | str | None = None, end_date: date | str | None = None,
    outputsize: int = DEFAULT_OUTPUTSIZE, client: TwelveDataClient | None = None,
    bronze_dir: Path = DEFAULT_MARKET_BRONZE_DIR,
    silver_path: Path = DEFAULT_MARKET_PRICES_PATH,
    now: datetime | None = None,
) -> MarketPricePipelineSummary:
    """Fetch through a safe boundary and store completed sessions only.

    The raw response is retained in Bronze before the completed-session guard.
    Silver is untouched if the provider returns a date on/after the safe boundary.
    """
    plan = build_market_ingestion_plan(
        start_date=start_date, end_date=end_date, outputsize=outputsize, now=now,
    )
    resolved_client = client or TwelveDataClient()
    fetch = resolved_client.fetch_daily(
        start_date=plan.start_date, end_date=plan.end_date, outputsize=plan.outputsize,
    )
    bronze_path, _, digest = save_market_bronze(fetch, bronze_dir=bronze_dir)
    incoming = normalize_market_prices(
        fetch, source_bronze_file=bronze_path.name, source_content_sha256=digest,
    )
    boundary = plan.safe_boundary_date
    if incoming.reference_date.map(lambda value: value >= boundary).any():
        raise ValueError(
            "Twelve Data returned a current or future session at/after the safe boundary; "
            "Bronze was preserved and Silver was not changed."
        )
    output = Path(silver_path)
    existing = read_market_prices(output) if output.exists() else pd.DataFrame(columns=incoming.columns)
    merged = merge_market_prices(existing, incoming)
    written = len(merged) - len(existing)
    write_market_prices(
        merged, output_path=output,
        source_bronze_files=sorted(set(merged.source_bronze_file.astype(str))),
    )
    dates = pd.to_datetime(incoming.reference_date)
    return MarketPricePipelineSummary(
        source=PROVIDER, ticker=TICKER, rows_received=len(fetch.payload["values"]), rows_written=written,
        earliest_reference_date=dates.min().date().isoformat(),
        latest_reference_date=dates.max().date().isoformat(),
        bronze_path=str(bronze_path), silver_path=str(output), content_sha256=digest,
        requested_start_date=plan.start_date.isoformat() if plan.start_date else None,
        requested_end_date=plan.end_date.isoformat(), safe_boundary_date=plan.safe_boundary_date.isoformat(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest completed daily MELI prices from Twelve Data.")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--outputsize", type=int, default=DEFAULT_OUTPUTSIZE)
    parser.add_argument("--dry-run", action="store_true", help="Print the validated plan without network or writes.")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.dry_run:
        plan = build_market_ingestion_plan(
            start_date=args.start_date, end_date=args.end_date, outputsize=args.outputsize, now=now,
        )
        print(format_market_ingestion_plan(plan))
        return
    result = run_market_price_pipeline(
        start_date=args.start_date, end_date=args.end_date, outputsize=args.outputsize, now=now,
    )
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
