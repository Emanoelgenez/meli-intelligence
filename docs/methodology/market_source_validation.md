# Market Source Validation — Sprint 5H

## Decision

**APPROVED_SOURCE = NONE**

No provider passed the source-acceptance gate. No Market client, transformation, Bronze writer, Silver writer, query module, Parquet or production pipeline was created. The Sprint 5G UI foundation remains unchanged.

## Baseline

- Worktree: `<LOCAL_USER_HOME>\.codex\worktrees\market-source-sprint-5h\invest`
- Baseline HEAD: `655b5f0289b3e7f2ca800d8a5a82bdcfb7b1025b`
- Baseline commit: `feat: add Market storytelling foundation`
- Initial working tree: clean
- Sprint 5G Market storytelling helper, page and methodology files were present.

## Stooq live probe

The probe used the project's existing `httpx` dependency, HTTPS, no API key, a 20-second timeout, and the daily `MELI.US` endpoint with a 30-calendar-day request window. No browser or manual interaction was used. No challenge was bypassed.

- HTTP status: **200**
- Content-Type: **`text/html; charset=utf-8`**
- Body prefix: `<!DOCTYPE html><html>...<noscript>This site requires JavaScript to verify your browser...`
- HTML / challenge: **yes**, JavaScript browser verification
- CSV response: **no**
- Expected CSV header (`Date,Open,High,Low,Close,Volume` or equivalent): **not present**
- Valid OHLCV observations: **none**; the apparent CSV rows were JavaScript challenge text and HTML
- Returned trading dates / numeric Close: **not available**
- N/D message: **not observed**
- API key or quota message: **not observed**; this probe does not establish whether an API key would remove the challenge
- Acceptance: **rejected** because the direct request did not return machine-readable market data and would require browser verification to proceed.

The response was inspected in memory only and was not persisted as Bronze or copied into fixtures. No payload values are treated as real market observations.

## Alpha Vantage fallback

- `ALPHA_VANTAGE_API_KEY` present: **no**
- `ALPHAVANTAGE_API_KEY` present: **no**
- Live tested: **no**
- Approved: **no**
- Result: **ALPHA_VANTAGE_NOT_LIVE_VALIDATED_NO_KEY**

No key was requested, read, logged or created. The API-key-required endpoint and free-tier limits were not live-validated in this environment; full-history access is not assumed to be free.

## Consequences for the data layer

The existing 5G catalog location remains an optional future path, not an ingested dataset. No Bronze raw payload exists, no real `market_prices` Silver schema has been registered, and there is no earliest or latest persisted trading date to report. No incremental merge or source-window claim can be made. Currency, ticker provenance and source lineage therefore remain unavailable rather than being inferred or fabricated.

Returns, valuation, market cap, P/E, EV/EBITDA, MELI34 prices and MELI-to-MELI34 conversion remain out of scope. No UI or 5G foundation changes were made in this sprint.

## Retest condition

Reconsider a provider only when a direct, credential policy-compliant request returns documented, machine-readable daily MELI observations and passes the criteria in the Sprint 5H source-validation brief. Stooq historical data reference: <https://stooq.com/db/h/>.
