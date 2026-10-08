# Financial Storytelling

## Purpose and scope

The Financial page answers: “What do MercadoLibre's reported financials say about growth, profitability, cash generation and balance-sheet position?” It presents normalized SEC Company Facts already persisted in Financial Silver, plus existing Financial-domain `INTERPRETATION` records when available. Company fundamentals remain separate from market and valuation data.

The page does not use MELI or MELI34 prices, market capitalization, trading returns, valuation multiples, or valuation models. It does not infer user behavior, engagement, retention, cross-sell, user overlap, or Product problems from financial results.

## Persisted facts and allowlists

The Silver dataset is `financial_facts`, stored at the canonical path exposed by the storage/catalog layer (`data/silver/sec/financial_facts.parquet`). Its persisted schema includes `metric_id`, `value`, `unit`, `period_start`, `period_end`, `period_type`, `period_label`, `source`, `form`, `filed_at`, and `accession_number`, along with SEC taxonomy and normalized filing lineage fields. The source is SEC EDGAR Company Facts API; normalized monetary facts use the reported USD unit.

The first-fold quarterly allowlist is:

- `net_revenues_financial_income` — revenue and financial income;
- `operating_income` — operating income;
- `net_income` — net income;
- `operating_cash_flow` — operating cash flow.

Supporting detail is restricted to persisted facts: `gross_profit`, `capex_productive_assets`, `cash_and_equivalents`, `total_assets`, `total_liabilities`, and `stockholders_equity`. The page does not discover arbitrary metric IDs. A missing allowlisted fact remains unavailable and is never shown as zero.

## Period and filing semantics

`period_end` is economic freshness; `filed_at` is filing context. Cards retain their own start/end dates, period type, source, unit and filing context, including form and accession number. Quarterly duration facts are selected for the first-fold cards and the primary revenue trend. Balance sheet context is selected only from `INSTANT` facts and is labeled as a point-in-time balance.

The UI does not reconcile SEC filings, choose amendments, resolve duplicate accessions, or restate Silver data. Duplicate economic keys are surfaced as errors rather than silently choosing a filing. `QUARTER`, `YTD`, `FY`, and `INSTANT` retain their stored meanings. The page does not sum quarters into annual values, divide annual values into quarters, or convert YTD into a quarter.

## Storytelling and presentation

The page order is context, freshness/status, at most four key reported facts, one primary quarterly revenue trend, supporting profitability/cash/balance-sheet facts, existing interpretations, and methodology. Supporting facts and full filing lineage are progressively disclosed. Currency is formatted using the persisted unit; no currency conversion occurs. Full stored precision and source lineage remain available in detail.

The revenue trend contains only persisted quarterly revenue observations in chronological order. Missing periods remain missing; the UI does not interpolate, resample, fill gaps, or calculate YoY, QoQ, CAGR, margins, FCF, cash conversion, leverage, or efficiency ratios.

Financial interpretations are selected only from persisted `INTERPRETATION` records whose business domain is Financial. The UI does not generate interpretations or relabel FACT/OBSERVATION records.

## Progressive disclosure

The first fold presents context, data status and freshness, and no more than four priority quarterly financial facts. It contains at most one primary trend. Additional profitability, cash generation and balance-sheet facts appear below the fold. Filing context, accession number, full precision and period details can be opened on demand. Existing interpretations follow the primary reported facts. Technical details stay available without competing with the executive reading, while missing and degraded states remain explicit. Progressive disclosure does not hide transformations or calculations: the UI performs no new financial calculations.

## Nielsen heuristics

The page applies Nielsen's usability heuristics in its financial context:

- **Visibility of system status:** freshness, dataset status and covered economic periods are visible.
- **Match between the system and the real world:** revenue, income, cash, balance-sheet facts and filing context use business language.
- **User control and freedom:** shared temporal filters let users change the period and reset through the application controls.
- **Consistency and standards:** Financial follows the visual hierarchy and status conventions of the other pages.
- **Error prevention:** missing is not zero; instant is not duration; quarter is not annual; and filing date is not the economic period.
- **Recognition rather than recall:** readable metric labels and period context are shown with reported values.
- **Flexibility and efficiency of use:** the summary comes before optional detail.
- **Aesthetic and minimalist design:** the first fold has at most four cards and one primary trend.
- **Help users recognize, diagnose and recover from errors:** degraded states are explicit, with Data Quality & Sources available for technical diagnosis.
- **Help and documentation:** period semantics are explained where needed.

### Accessibility

For accessibility, the page does not depend on color semantics: green or red is never the only indicator. Status and metric meanings have explicit text labels, headings follow a clear hierarchy, and technical details are available through progressive disclosure. Emojis are not used as the sole status marker.

## Company fundamentals, market and valuation boundary

Financial Storytelling covers COMPANY fundamentals. It does not incorporate market data or valuation: no share price (including MELI or MELI34), market cap, stock return, P/E, EV/EBITDA, or valuation multiples are used. Those belong to a separate market/valuation layer.

## Product inference boundary

Financial facts alone do not demonstrate user behavior, engagement, retention, overlap, cross-sell, or a Product problem. Financial Storytelling does not turn reported financial results into an inference about product behavior.

## Filters and degraded data

Shared date filters apply to economic `period_end`; a selected global domain does not change the meaning of this Financial page. Invalid date ranges are rejected by the shared `FilterState` contract. Missing, empty, or unreadable datasets produce explicit availability messages and the page remains renderable. No synthetic data or zero fallback is used. Data Quality & Sources remains the technical diagnosis view.

## Methodological limits

The page is a thin, read-only presentation layer. Analytics are displayed only if already persisted in an established dataset; inspection found no Financial analytics Gold dataset or query/catalog entry, so this page does not calculate or display derived growth, margins, FCF, or ratios. Financial performance alone does not establish customer behavior, causality, or a Product recommendation.
