# Commerce and Fintech Storytelling

## Purpose and audience

The Commerce page answers: “What does reported evidence say about the scale,
activity and trajectory of MercadoLibre Commerce?” The Fintech page asks the
same question about Mercado Pago / MercadoLibre Fintech. Both pages are concise
domain views for business readers investigating reported evidence. They do not
answer what the company should build.

## Data sources and metric allowlists

Pages read existing local datasets only through the UI data-access layer and
existing DuckDB query modules. The current facts come from `operational_kpis`
(`data/silver/sec/operational_kpis.parquet`) and, for Fintech credit context,
`extended_operational_kpis`
(`data/silver/sec/extended_operational_kpis.parquet`). Existing interpretations
are read from the Evidence Gold dataset when available. The UI never calls
sources, ingestion or pipeline code, accesses the internet, or writes data.

The deterministic Commerce allowlist is `gmv`, `unique_active_buyers`, and
`items_sold`, in that presentation priority. The Fintech allowlist is
`fintech_mau`, `tpv`, `aum`, `credit_portfolio`, and `npl_15_90_total`; the first
four are the overview card priority, and the 15–90 day NPL is secondary detail.
These IDs are present in the operational/extended operational transformations
and tests. `items_per_buyer`, `gmv_yoy_growth`, `fintech_mau_yoy_growth`, and
other analytics are calculated by existing analytics functions but are not
persisted in a catalogued operational Gold dataset, so these pages do not
recompute or present them.

## Snapshot and trajectory

Each priority metric selects its own latest reported row within the selected
date interval. A card keeps its own source period, reference date, source and
full loaded precision; different metrics need not share a reference date.
Source `period_label` and `period_type` remain visible so quarterly, YTD or
instant values are not made to look monthly. An absent metric is omitted and
listed as unavailable; no zero or substitute is fabricated.

At most one reported time series is shown per page: GMV for Commerce and TPV for
Fintech. The chart contains only available source observations in chronological
order. It does not fill missing periods, interpolate, resample, or calculate
YoY, QoQ, CAGR or moving averages. No dual axis, pie, donut, gauge, radar or
decorative chart is used.

## Freshness, filters and degraded states

Domain freshness is the latest eligible `reference_date`/`period_end` within
the current date filter. Filing date is not presented as the economic
reference date. Shared start/end date filters are validated by the existing
`FilterState`; the page is already semantically fixed to Commerce or Fintech,
so the global business-domain selector does not hide its facts. The shared
reset action remains available.

Missing, empty and invalid source datasets are shown as explicit textual
degraded states with a pointer to Data Quality & Sources. Partial data remains
usable. A missing interpretation or metric is not treated as zero and does not
break the page. No synthetic fallback is used.

## Evidence and interpretations

The pages display up to three existing rows whose `evidence_type` is exactly
`INTERPRETATION`, when the source data supports domain filtering. They do not
turn observations into interpretations or generate new claims. Each item keeps
its claim, metric, source and reference date visible. Evidence details and
reported precision are available on demand through expanders.

## Commerce and Fintech are separate aggregate series

Reported Commerce and Fintech metrics are aggregated separately. Simultaneous
growth does not establish that the same users are present in both domains,
user-level overlap, cross-domain retention, individual activity frequency,
cross-sell, or a count of ecosystem users. These aggregates also do not
establish causality between Commerce and Fintech. The UI does not estimate
overlap or combine the series into an engagement/ecosystem score. Those
questions require appropriate user-level evidence and belong in Product
Evidence/discovery, where they remain hypotheses and questions rather than
facts.

Fintech 15–90 day NPL is shown only as reported credit-quality context and is
not turned into a recommendation. It is distinct from BCB's household
delinquency measure above 90 days.

## Storytelling and progressive disclosure

Both pages follow context → freshness/data status → key metrics → reported
trajectory → existing interpretations → next exploration. The first view is
limited to a short question, latest reference date, clear status and at most
four priority metrics. The trajectory is one simple line chart. Source details,
full precision and methodology are below the fold in expanders; this keeps the
business narrative legible while allowing audit when needed.

## Nielsen, accessibility and consistency

- **Visibility of system status:** latest reference date and missing/empty/
  invalid states are explicit.
- **Match with the real world and recognition over recall:** business labels
  and readable units are used instead of raw metric IDs/backend units.
- **User control and error prevention:** shared reversible date filters use
  the existing validation contract.
- **Consistency:** Commerce and Fintech share the same snapshot, card, date,
  source and status conventions.
- **Flexibility and minimalist design:** a short summary comes first; up to
  four cards, one chart and up to three existing interpretations limit visual
  load.
- **Error recovery and help:** degraded messages point users to Data Quality &
  Sources, and short captions explain the source-period context.

Status and chart meaning do not depend on color alone. Visible text labels,
short copy and readable contrast support accessibility. Values are never
colored or described as good/bad based only on direction.

## No causal inference or Product recommendation

These pages present facts and already-reviewed interpretations only. They do
not infer behavior, causes, user overlap, product problems, opportunities,
solutions, features, priorities or recommendations. “Next exploration” directs
the reader to existing evidence and data quality, not to a product decision.
