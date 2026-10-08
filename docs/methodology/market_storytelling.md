# Market Storytelling

## Central question and audience

The Market page asks: “What does the market data say about MELI's price behavior and valuation context, without confusing market movements with business fundamentals?” It is a market-data view, not a company-fundamentals or investment-advice page.

## Story and current page behavior

The intended sequence is context, data status and latest trading date, latest persisted closing price, persisted price trend, market-data limitations, valuation status and methodology. Twelve Data is approved for internal/local ingestion; the optional market dataset may still be absent in deployments without locally configured credentials/data. The page does not manufacture cards, a price chart, returns or multiples when source data is absent.

When the compatible persisted dataset is available, the page can show a few price facts and one close-price trend. It preserves observed trading dates, currency, source and provenance. It does not fill holidays or missing sessions, interpolate, resample, or calculate returns in the UI. Freshness uses the latest persisted `reference_date`; a current or partial session must not advance it. The ingestion boundary uses the current civil date in `America/New_York`, while actual returned observations remain provider trading dates; weekends/holidays are not resolved with a locally invented calendar. Retrieval timestamps remain technical provenance and do not replace the latest market reference date. Public redistribution rights are not implied; terms must be reviewed before a public Streamlit deployment.

### Trading dates and interpolation

Persisted trading dates are preserved exactly. Days without trading remain absent: no interpolation, artificial calendar filling, or resample occurs in the UI. The chart line connects only existing observations and does not create an intermediate price.

### Degraded states

`MISSING`, `EMPTY` and `INVALID` are explicit degraded states. The `market_prices` dataset is optional, so a missing file does not break the application. Missing Market data never becomes a zero price, creates no synthetic observation, and does not create valuation. Valuation remains explicitly unavailable until persisted inputs and an approved methodology exist. Data Quality & Sources remains the place for technical diagnosis.

## Company and market separation

Company facts and operational KPIs remain separate from Market. This page does not automatically join prices to financial filings or operating indicators, and it does not state that price movements were caused by GMV, TPV, MAU, revenue or other business metrics. If a future company-fact join is approved, look-ahead must be prevented by respecting the filing date.

MELI is the company share ticker. MELI34, if added later, is a Brazilian market instrument/BDR and not a separate operating company. No MELI34 company fundamentals or parity conversion are inferred.

## Progressive disclosure, Nielsen and accessibility

The top-level view is limited to status, latest trading date and a small amount of persisted price evidence. Source URL and technical retrieval provenance sit in details. Missing, empty and invalid states are explicit, with Data Quality & Sources available for diagnosis.

The page follows Nielsen heuristics: visibility of system status (dataset status and latest trading date), match to real-world language (ticker, price and currency labels), user control (shared date filters), consistency with the existing page hierarchy, and error prevention (missing is not zero; market observations are not fundamentals). Minimalism limits the view to few cards and at most one chart; no color-only performance meaning is used.

Accessibility includes text labels for status and currency, hierarchical headings and no green/red buy/sell framing. No emoji is the sole status indicator. Detail disclosure must make technical source context available without hiding availability limitations.

## Valuation and investment limits

Valuation remains unavailable until a reliable market price, shares outstanding and temporally comparable financial inputs are persisted with clear definitions. No P/E, EV/EBITDA, market cap, target price, fair value, trading signal or recommendation is inferred. The page provides no buy, sell or hold advice.
