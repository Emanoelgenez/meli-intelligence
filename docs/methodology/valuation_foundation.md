# Valuation Foundation (Sprint 6A)

## Separation of Company and Market

Company fundamentals remain the SEC financial facts layer. Market prices remain daily MELI observations in USD. This module defines analytical availability and filing-safe alignment only; it does not merge Market prices into Company facts or use Product Evidence.

## Authoritative inputs and current availability

The SEC Company Facts client retrieves and preserves the complete official `facts` object. Financial normalization previously mapped only selected `us-gaap` concepts into its USD-only Silver schema, so it could not represent share counts. Sprint 6B adds a separate extractor for the explicit SEC DEI concept `dei:EntityCommonStockSharesOutstanding`, unit `shares`, as an instant Company fact. It preserves entity, reference date, value, unit, filing date, accession number, source and official Company Facts URL. It does not place shares in the USD financial-facts schema.

The official SEC source contract was live-validated in the preceding Market-cap foundation work; this valuation-consumption sprint uses offline synthetic fixtures only and does not read ignored local data. No share count is guessed, backsolved or hard-coded. Diluted EPS denominators are not substitutes: they are weighted-average period denominators for per-share earnings, not an explicit point-in-time shares-outstanding fact. MELI34/BDR conversion assumptions are also excluded.

A share price alone cannot establish company market capitalization. The upstream Gold calculation multiplies an exact MELI USD close by an explicit, eligible SEC share-count fact only. Valuation now consumes the persisted Market Cap Gold output rather than reconstructing market cap from source data. The Gold observation preserves the input metric IDs and SEC/Market provenance.

`build_valuation_snapshot` selects the latest MELI/USD Market Cap Gold row whose `reference_date` is on or before the requested valuation date. A future observation is excluded. The latest eligible row is selected before its status is checked: if that row is unavailable, the snapshot stays unavailable and does not fall back to an older numeric market cap. No interpolation or synthetic Market date is introduced. The selected Gold reference date, original Gold status, methodology version and source metric IDs remain visible in the typed snapshot.

Without an eligible market-cap input, candidate metrics return an explicit unavailable status, `value=None`, and a deterministic reason. With an AVAILABLE persisted Gold observation and a positive, eligible USD instant stockholders' equity fact, price-to-book is `market_cap / book_value`. Equity is selected through the existing `select_financial_fact_as_of` contract and its filing date must be no later than the requested valuation reference date. Future-filed equity is excluded and reported as look-ahead prevented; missing and nonpositive denominators have separate unavailable states. The metric preserves Market/SEC source metric IDs and the selected share-count/equity accession numbers.

Price-to-sales and price-to-operating-cash-flow remain unavailable because the currently supported quarterly duration facts are not a trailing-twelve-month denominator; one quarter is not annualized and does not become TTM. They return `UNAVAILABLE_PERIOD_MISMATCH` when a quarter exists without a valid TTM contract. No unavailable ratio is represented as `0.0x`. P/E is not implemented.

## Period and filing-date alignment

`select_financial_fact_as_of` is a pure helper for the candidate denominator facts. It selects only canonical USD facts whose `filed_at` and `period_end` are on or before the Market reference date. Quarterly duration facts are required for revenue and operating cash flow; stockholders' equity must be an `INSTANT` fact with no `period_start`. YTD, FY, OTHER and duration/instant substitutions are not silently aligned. Invalid, missing or ambiguous alignment returns `None`.

The selected SEC Silver row contains the latest normalized filing for an economic period. If that row was filed after the requested Market date, it is excluded; this layer does not reconstruct an earlier filing version from first-reported metadata. For shares outstanding, eligible facts require both `reference_date <= market_reference_date` and `filed_at <= market_reference_date`. Selection orders reference date descending, filing date descending and accession number descending, matching the SEC normalizer's latest-filing tie-break. This prevents look-ahead bias. Financial facts are never forward-filled, and Market prices are not interpolated.

## Scope limits

This is not fair value, target price, DCF, forecast, trading signal, or buy/sell guidance. It does not infer Product behavior or create hypotheses from stock price or market capitalization. MELI34 remains a market instrument, not a source of company fundamentals; no MELI/BDR conversion is performed. A future valuation metric can become available only after authoritative market capitalization and compatible, filed financial denominators are supplied under a documented methodology.
