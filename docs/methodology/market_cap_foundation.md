# Authoritative Market Capitalization Foundation (Sprint 6B)

## Source and fact contract

The project reuses the official SEC EDGAR Company Facts endpoint already used for MercadoLibre financial facts. The SEC client validates the response envelope and retains the complete `facts` payload in Bronze; it does not restrict the payload to the financial transformation's concept allowlist. The existing financial transformation selected only `us-gaap` monetary concepts, and its Silver schema requires USD. That schema is not suitable for a share count.

Sprint 6B recognizes the explicit SEC DEI taxonomy/concept `dei:EntityCommonStockSharesOutstanding` and requires the `shares` unit. It is modeled separately as an instant Company fact with entity, metric/concept, reference date, value, unit, `filed_at`, accession number, form, source and SEC Company Facts URL. The supported extraction from a Company Facts-shaped payload is offline-testable. A controlled live validation in Sprint 6C confirmed an eligible MELI fact for reference date 2026-08-05, filed 2026-08-06, accession `0001099590-26-000023`, with 50,696,802 shares. Sprint 6D tests use synthetic fixtures only and do not persist or depend on the live payload. If no explicit DEI observation is present, the result remains unavailable.

The concept's `end` date is the economic reference date. The filing date determines when the fact became publicly usable. For a Market observation on date D, both the share-count reference date and `filed_at` must be no later than D. The latest eligible fact is selected by reference date descending, filing date descending and accession number descending. The accession ordering is a stable tie-break consistent with the existing SEC Company Facts normalizer. Future filings are never used.

## Silver share-count storage

Sprint 6D persists normalized `dei:EntityCommonStockSharesOutstanding` as a dedicated Company Silver dataset at `data/silver/company/shares_outstanding.parquet`; it is not mixed into monetary financial facts. The Silver contract preserves entity, metric and SEC taxonomy/concept, reference date, positive whole-share value, unit, filing date, accession number, form, source and source URL. Bronze filename and payload SHA-256 are retained when those fields are supplied by the caller; storage does not invent missing provenance.

The deterministic fact identity is `entity + taxonomy + concept + unit + reference_date + filed_at + accession_number`. This permits separately filed revisions of an economic date to remain distinguishable. Exact semantic replays under that key deduplicate deterministically, while disagreement in material fact or source fields under the same key raises an explicit conflict. Silver writes use the repository's atomic Parquet replacement convention and are safe to replay.

## Derived Gold market capitalization

Market capitalization is a derived Gold observation, not SEC source data and not Silver. The Gold builder combines each exact persisted MELI Market price observation with the latest eligible SEC shares fact using the existing authority and no-look-ahead selector. It preserves the market and share-count provenance references and emits an explicit unavailable status when authoritative inputs are absent or incompatible. It never interpolates or forward-fills Market prices and never estimates shares.

The 6D Gold storage uses `data/gold/market/market_capitalization.parquet`, keyed by `ticker + reference_date`. Replaying a semantically identical derived observation is idempotent; a material disagreement for the same Market key fails explicitly. This remains limited to MELI/USD market capitalization context and does not make P/E, P/S, price-to-cash-flow, fair value, a target price or a recommendation available by itself. MELI34 remains excluded and receives no Company fundamentals.

## Market capitalization calculation

The pure helper computes only:

`market capitalization = exact MELI USD close × eligible authoritative SEC shares outstanding`

It accepts MELI only, requires USD, finite positive price and finite positive shares, and reports named unavailable statuses for missing shares, look-ahead, invalid inputs, currency mismatch or unsupported ticker. It does not forward-fill or interpolate prices. The output includes the market close and DEI metric IDs as lineage.

## Valuation availability

Valuation availability accepts an optional market-cap result. No market cap means candidate ratios stay explicitly unavailable. Price-to-book may be computed only with a positive eligible SEC instant stockholders' equity fact. Price-to-sales and price-to-operating-cash-flow remain unavailable because the supported quarterly revenue/operating-cash-flow facts are not trailing-twelve-month denominators; a single quarter is not silently treated as an annual denominator. P/E is outside this sprint.

Diluted EPS denominators are not accepted as shares outstanding because they are weighted-average period inputs used in earnings-per-share computation, rather than a point-in-time share-count fact. No share count is inferred from price, EPS, equity, third-party data, or MELI34. MELI34 is a BDR/market instrument and is not given separate company fundamentals; no conversion ratio is assumed.

## Scope limits

This foundation does not produce fair value, target price, DCF, forecast, trading signal, or buy/sell recommendation. It does not infer Product behavior or generate Product Evidence from price or market capitalization. Sprint 6D adds only the synthetic-tested storage and deterministic Gold contracts; no live payload or ignored local data is included in the change.
