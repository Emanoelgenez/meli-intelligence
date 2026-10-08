# Macro, PESTEL and SWOT Storytelling

## Purpose and central questions

These read-only pages present already-persisted Macro indicators and
evidence-backed PESTEL/SWOT classifications. They are intended for business
readers who need a concise view of evidence and its coverage.

- **Macro:** “What does the current Brazilian macro environment say about the
  operating context around MercadoLibre?”
- **PESTEL:** “Which external forces are supported by the current evidence
  base?”
- **SWOT:** “Which evidence-backed internal and external factors are currently
  classified as strengths, weaknesses, opportunities or threats?”

The pages do not answer what MercadoLibre should do.

## Datasets and actual metric IDs

The UI reads the catalogued datasets through `ui.data` and existing query
modules. It does not access source clients, ingestion, transformations or
pipelines, and it does not write data.

- Macro Silver: `macro_indicators` (`metric_id`, `source_series_id`,
  `reference_date`, `value`, `unit`, `frequency`, `source`, `source_url`,
  retrieval/ingestion metadata).
- Macro Gold: `macro_analytics` (`metric_id`, `reference_date`, `value`,
  `unit`, `frequency`, `source`, `source_metric_id`, `analytics_kind`,
  `definition_context`, temporal comparison fields and direction flags).
- Macro observations: `macro_evidence` (`evidence_id`, `evidence_type`,
  `business_domain`, `metric_id`, `reference_date`, `claim`, `claim_kind`,
  `source`, `source_metric_id`, `is_interpretation`, and context/version).
- Existing interpretations: common Evidence registry schema, filtered to
  `evidence_type=INTERPRETATION` and Macro domain.
- Strategy Gold: existing PESTEL and SWOT Parquets and their stored schemas.

Real Macro Silver IDs inspected in the Sprint 3G analytics contract are:
`selic_target_annual`, `selic_effective_annual_252`,
`ipca_monthly_change`, `ipca_12m_change`, `usd_brl_sell_rate`,
`household_free_credit_balance`, `household_free_credit_npl_90d_rate`,
`ibc_br_activity_sa_index`, `unemployment_rate_rolling_3m`,
`retail_sales_volume_mom_sa`, `pix_transactions_count_monthly`, and
`pix_transactions_value_monthly`.

Persisted derived Macro IDs used for supplemental context include
`selic_target_change_pp`, `ipca_12m_change_pp`, `usd_brl_month_end`,
`usd_brl_monthly_change_pct`, `household_free_credit_balance_yoy_growth`,
`household_free_credit_npl_90d_yoy_change_pp`,
`ibc_br_activity_mom_change_pct`, `unemployment_rate_change_pp`,
`pix_transactions_count_yoy_growth`, and
`pix_transactions_value_yoy_growth`.

## Macro allowlist, priority and freshness

The first view uses a fixed, ordered allowlist of four IDs:

1. `selic_target_annual`
2. `ipca_12m_change`
3. `usd_brl_sell_rate`
4. `unemployment_rate_rolling_3m`

Cards use the latest available observation for each metric inside the shared
date interval. Each card retains its own reference date, source, unit and
frequency. Missing values are omitted and named as unavailable, never changed
to zero. The UI does not infer labels from arbitrary future registry entries.

Latest applicable reference date is calculated from the allowlisted facts and
already persisted analytics, using `reference_date`. Retrieval time is not a
measure of economic freshness. Date filters reuse and validate `FilterState`.

## Macro trajectory, units and frequency

The single primary chart is the persisted daily `selic_target_annual` series.
Dates and values are ordered chronologically. No monthly resampling, gap
filling, interpolation, dual axis or UI-side YoY/QoQ/change calculation is
performed. Its daily frequency is stated in the caption.

Labels use readable units for annual rates, percentages, percentage points,
BRL/USD, index points, Pix transactions and monetary values. Raw values and
source precision remain available in the detail expander. `usd_brl_month_end`
is eligible only as a prebuilt Gold value; the UI never reconstructs the
month-end selection.

Other allowlisted context is below the fold: IBC-Br, official retail monthly
change, household free-credit balance, BCB household delinquency above 90
days, Pix count/value, and persisted derived changes for those subjects. Those
analytics are read from Gold without recomputation. IBC-Br is described as an
economic activity indicator, not GDP. Unemployment is a rolling-three-month
publication with overlapping windows. BCB delinquency above 90 days is not
equivalent to MercadoLibre's 15–90 day NPL.

## PESTEL coverage and lineage

PESTEL records use the stored schema: `pestel_id`, `pestel_dimension`,
`business_domain`, `reference_date`, period/entity fields, `claim`,
`classification_rationale`, `source_evidence_ids`,
`source_evidence_types`, `source_metric_ids`, `source`,
`is_interpretation`, `methodology_version`, and `definition_context`.

The fixed display order is Political, Economic, Social, Technological,
Environmental, Legal (stored enum values are uppercase). Coverage counts and
claims are computed from persisted classifications only. An absent dimension
stays absent; no six-dimension completeness is forced. A few claims appear
first; full lineage and additional items are available on demand. Evidence
IDs, Evidence types, source metric IDs, rationale, source and period remain
available for audit.

The UI does not re-run PESTEL rules. Macro indicators retain their existing
classification, and Pix is not relabeled as Technological simply because it
uses digital infrastructure.

## SWOT coverage, scope and lineage

SWOT records use the persisted schema: `swot_id`, `swot_category`,
`business_domain`, `reference_date`, period/entity fields, `claim`,
`assessment`, `classification_rationale`, Evidence IDs/types/metric IDs,
PESTEL IDs/dimensions, `source`, methodology/context, `scope`, and
`is_interpretation`.

The display order is Strength, Weakness, Opportunity, Threat. The UI separates
records using their persisted `scope` (`INTERNAL`/`EXTERNAL`) and shows each
persisted category. Strength/Weakness remain internal classifications;
Opportunity/Threat remain external classifications under the stored SWOT
contract. Macro is never reclassified by the UI. Numeric sign is never used to
create or alter a category. Missing categories are acceptable and empty
quadrants are not populated artificially.

Source Evidence lineage and, for external records, PESTEL lineage are hidden
from the first view but available in item details. Claims, assessments,
rationale, dates and sources are preserved from the stored records.

## Existing Evidence and interpretations

The Macro page may show persisted `OBSERVATION` rows from `macro_evidence` and
up to three existing common Evidence interpretations. It never turns an
Observation into an Interpretation or creates a new interpretation. PESTEL
and SWOT pages show only their persisted classifications and linked claims.

## Storytelling, progressive disclosure and Nielsen

Macro follows context → freshness/status → four priority conditions → one
temporal view → existing Evidence/interpretations → additional context →
methodology. PESTEL starts with coverage and selected claims; SWOT starts with
coverage and a small internal/external classification view. Full tables and
lineage sit in expanders to keep the first view focused.

- **Visibility of system status:** reference dates, coverage and MISSING,
  EMPTY, INVALID or read-failure states are textually identified.
- **Match with the real world / recognition over recall:** user-facing labels
  describe economic and strategic concepts rather than raw IDs.
- **User control / error prevention:** shared date filters reuse the validated
  filter contract; invalid intervals do not silently change meaning.
- **Consistency:** all pages use the same freshness, source, date and degraded
  state conventions established in 5A–5C.
- **Flexibility / minimalist design:** summary first, detailed evidence on
  demand; four Macro cards, one chart and only a few initial claims.
- **Error recovery / help:** missing data is explained and source coverage is
  discoverable; short captions clarify frequency and definitions.

Text labels carry status and category meaning; colors are not the sole signal.
SWOT Strength/Weakness is not encoded as green/red. Labels and captions remain
visible for accessibility.

## No causal inference or recommendation

These pages report existing values and classifications. They do not create
new mechanisms such as “Selic caused” or “Pix drove,” do not infer that Macro
conditions caused MercadoLibre outcomes, and do not provide recommendations,
features, priorities or Product solutions. PESTEL and SWOT are evidence
synthesis layers, not prescriptions.
