# Market Data Foundation

## Infrastructure investigation and source decision

Sprint 5H manually validated the free-tier Twelve Data `/time_series` endpoint for MELI: HTTP 200 JSON, 1day observations with valid OHLCV, currency USD and exchange NASDAQ. The probe returned 20 real trading observations and required an API key. The approved source is **TWELVE_DATA** for local development, internal ingestion and internal analysis. Stooq was not approved because automated CSV access could not be validated without browser verification. No live response is included in tests.

The client calls `https://api.twelvedata.com/time_series` with `symbol=MELI`, `interval=1day`, `format=JSON`, `adjust=none`, and a conservative default `outputsize=100`. Optional `start_date` and `end_date` boundaries are supported; no inclusivity semantics are assumed for `start_date`. For this daily endpoint, `end_date` behaves as a maximum datetime boundary: a date-only value does not necessarily include that day's candle. Output size is configurable; no unlimited or premium history is promised. Set `TWELVE_DATA_API_KEY` in the process environment before running the manual ingestion command. The key is sent only with the HTTP request: it is not stored in source, raw metadata, provenance URLs, errors, summaries, or logs.

## Separation and current availability

Company fundamentals (`financial_facts`), operational KPIs, macro context and Evidence remain separate from MARKET data. `market_prices` remains optional for deployments without local source credentials/data. The Market page is read-only and reports `MISSING`, `EMPTY` or `INVALID` when appropriate. Valuation is not implemented and is not made available by price ingestion.

The Silver schema is typed Parquet at `data/silver/market/market_prices.parquet`: `ticker`, `entity`, `reference_date`, `open`, `high`, `low`, `close`, nullable `volume`, `currency`, `exchange`, nullable `mic_code`, `source`, sanitized `source_url`, `retrieved_at`, `source_bronze_file` and `source_content_sha256`. Provider metadata supplies currency and exchange; code does not infer currency from price. Bronze preserves the exact JSON bytes and records provider, request symbol/interval/date window/outputsize, UTC retrieval time, sanitized URL and SHA-256 digest. Bronze filenames include retrieval time and a digest and refuse overwrites.

The economic key is `(ticker, reference_date)`. Identical replay rows are idempotently ignored while preserving the existing row's lineage. Conflicting OHLCV, currency or exchange values for the same key fail explicitly. Incremental merge appends new trading dates and retains older history even when the provider returns only a compact recent window. Rows are sorted by ticker and trading date. Trading-date gaps remain gaps: there is no interpolation, resampling, calendar filling, return calculation or valuation calculation.

### Observed daily boundary behavior and completed sessions

The live validation on 2026-10-06 established the following provider behavior; it is an observation, not a guarantee of future availability. The first request used `end_date=2026-10-05` and `outputsize=100`: Silver contained 100 rows spanning 2026-05-12 through 2026-10-02. The next request used `end_date=2026-10-06` and the same output size: it received 100 observations and wrote exactly one new economic key, 2026-10-05. Silver then contained 101 rows spanning 2026-05-12 through 2026-10-05; 2026-10-06 was absent. Existing history and its lineage were preserved, the new row referenced the second Bronze payload, and the API key was absent from persisted artifacts.

For a controlled ingestion intended to include a completed session D, use a boundary later than D, following the provider's observed semantics. Future automation must persist only completed sessions. It must not persist a daily candle for the current session while the market is open or while the observation may still change. Since `(ticker, reference_date)` is the economic key and the pipeline rejects conflicting values for an already stored key, excluding a partial candle prevents it from conflicting with the final candle for that date.

### Daily operations and safe boundary

The operational pipeline resolves its safe boundary to the current civil date in `America/New_York`, using the standard library timezone database. This is a query boundary, not a prediction of the latest trading session. An explicit `end_date` may be historical or equal to the safe boundary, but cannot be later. The pipeline additionally requires every transformed `reference_date` to be strictly earlier than the safe boundary. If Twelve Data unexpectedly returns a session on or after it, the raw fetch is retained in Bronze for provenance, the run fails clearly, and Silver is left untouched.

Weekends and exchange holidays use the same New York civil boundary. No local trading or holiday calendar is maintained: the provider may return the prior real trading session, and the absence of a calendar date is not interpreted as a missing session. Dry-run validates and prints the plan without requiring a key, making HTTP, or writing files. For a real fetch, Bronze records each distinct retrieval; Silver remains idempotent by economic key, so `rows_written=0` on an unchanged replay is a successful outcome and does not remove the Bronze record. Freshness remains factual: report the latest stored `reference_date`, safe boundary and retrieval time without labeling data stale based on civil-day differences.

The only displayed entity is `MercadoLibre, Inc.` under ticker `MELI`. A future `MELI34` series, if separately sourced, would be treated as a Brazilian market instrument/BDR. It would not receive company revenue, profit, GMV, TPV, MAU or balance-sheet fundamentals, and no MELI-to-MELI34 parity conversion would be inferred.

## Valuation boundary

Valuation is unavailable until reliable price and shares-outstanding data plus temporally comparable company fundamentals are persisted. No market capitalization, P/E, EV/EBITDA, valuation multiples, returns, cumulative returns or volatility are synthesized. If market data is joined to company facts in a future scope, a financial fact cannot be used before its filing date. This sprint performs no such join and no backtest.

Market price and company performance are different dimensions. The page makes no causal claims about prices and operating KPIs, does not infer user behavior, and does not produce buy/sell/hold guidance, target prices, trading signals or investment advice.

## Use, licensing and scope

This source approval is limited to local development and internal analysis. It does not establish a right to publicly redistribute price data through Streamlit Community Cloud; licensing and redistribution terms must be reviewed before any public demo. The dataset contains MELI only. MELI34/BDR ingestion, parity conversion, company fundamentals for the BDR, market returns and all valuation metrics remain out of scope.
