# Macro Analytics and Evidence

## Scope and evidence stages

This layer accepts normalized Macro Silver rows as a DataFrame, computes a
small, deterministic set of derived series, and creates source-grounded
observations. It performs no network access. The stages remain:

`FACT → OBSERVATION → INTERPRETATION → HYPOTHESIS → PRODUCT DISCOVERY QUESTION`

Sprint 3G stops at OBSERVATION. A reported fact remains a fact; an analytic
calculation is labeled as derived and records its source metric, formula,
period-matching rule, prior value/date where applicable, and methodology
context. Observation text states the measured fact only. This layer does not
create an interpretation, hypothesis, recommendation, product problem, or
causal claim.

## Derived metrics

| Derived metric | Source | Calculation | Unit |
| --- | --- | --- | --- |
| `selic_target_change_pp` | `selic_target_annual` | Current less immediately previous time-ordered observation | `percentage_points` |
| `ipca_12m_change_pp` | `ipca_12m_change` | Current less previous calendar month | `percentage_points` |
| `usd_brl_month_end` | `usd_brl_sell_rate` | Last available daily observation in each month | `brl_per_usd` |
| `usd_brl_monthly_change_pct` | Monthly USD/BRL snapshot | `(current / previous calendar month - 1) × 100` | `percent` |
| `household_free_credit_balance_yoy_growth` | `household_free_credit_balance` | `(current / same calendar month prior year - 1) × 100` | `percent` |
| `household_free_credit_npl_90d_yoy_change_pp` | `household_free_credit_npl_90d_rate` | Current less same calendar month prior year | `percentage_points` |
| `ibc_br_activity_mom_change_pct` | `ibc_br_activity_sa_index` | `(current / previous calendar month - 1) × 100` | `percent` |
| `unemployment_rate_change_pp` | `unemployment_rate_rolling_3m` | Current less previous published observation | `percentage_points` |
| `pix_transactions_count_yoy_growth` | `pix_transactions_count_monthly` | `(current / same calendar month prior year - 1) × 100` | `percent` |
| `pix_transactions_value_yoy_growth` | `pix_transactions_value_monthly` | `(current / same calendar month prior year - 1) × 100` | `percent` |

The reported monthly IPCA metrics and seasonally adjusted retail MoM metric
are not recalculated. Relative growth is not used for Selic or NPL rates.
Credit/Pix YoY rows with a zero prior-year denominator are omitted; no
division is performed. Missing comparison periods produce no derived row.

## Temporal matching

The input economic key `metric_id + reference_date` must be unique. Values
must be numeric and finite; source units and frequencies must match their
registered semantics. The calculation sorts by economic date and does not
forward-fill, backfill, interpolate, or invent periods.

Monthly YoY comparisons match `(year - 1, same month)`, not a 365-day offset
and not a positional `shift(12)`. Thus February 2024 month-end
`2024-02-29` matches February 2023 `2023-02-28`; February 2025
`2025-02-28` matches leap-year February 2024 `2024-02-29`.

Monthly MoM comparisons require the previous calendar month. January matches
December of the previous year. If that exact calendar month is absent, no
result is emitted. IPCA, IBC-Br, and Pix use calendar month-end Silver dates.

Selic changes use the immediately preceding observation after chronological
sorting, even if the source dates are not uniformly spaced. Unemployment
changes compare consecutive published observations. Unemployment is a
monthly publication of a rolling three-month estimate; consecutive windows
overlap and are not independent samples.

## USD/BRL month-end

For each calendar month, `usd_brl_month_end` selects the last daily quote
available in that month. The selected source date is kept in
`source_reference_date` and the derived `reference_date` is set to the
calendar month-end. For example, a last quote dated December 29 is stored as
the month-end observation dated December 31, with December 29 retained as its
source observation date. The monthly percentage change compares these
snapshots across adjacent calendar months. No monthly average or volatility
is calculated.

## Direction flags

Direction fields are deterministic descriptions of the sign of a derived
change, not assessments. The allowed labels are `rising`, `falling`,
`unchanged`; inflation uses `accelerating`/`decelerating`; FX uses
`depreciating_brl`/`appreciating_brl`; and credit/Pix count use
`expanding`/`contracting`. A positive USD/BRL change means more BRL per USD
and is labeled `depreciating_brl`. No good/bad, risk, favorable, opportunity,
or stress label is produced. There is no composite macro score.

## Specific definition boundaries

- BCB household credit NPL is overdue **more than 90 days**. MercadoLibre's
  `npl_15_90_total` covers **15–90 days**. They are distinct measures and
  are not directly compared or combined.
- The IBC-Br output describes activity measured by the seasonally adjusted
  IBC-Br series. It is not labeled as official GDP growth.
- The unemployment rate represents a rolling three-month period ending in
  the reference month, not a single-month independent estimate.
- Correlation is an optional descriptive statistic, requires explicitly
  matching daily or monthly frequencies and aligned periods, and reports the
  number and date range of aligned observations. It does not establish
  causality. No batch correlation matrix, ranking, or regression is created.

## Observations and Gold

`build_macro_observations` produces one deterministic SHA-256-identified
OBSERVATION per input fact and derived analytic. Every row has
`evidence_type=OBSERVATION`, `business_domain=Macro`, and
`is_interpretation=False`. Claims are literal descriptions of the value,
change, period, and source metric. There are no interpretation, hypothesis,
recommendation, or causal-claim fields.

Derived analytics and observations are persisted separately under
`data/gold/macro/` as ZSTD Parquet with fixed Arrow schemas and atomic file
replacement. Analytics identity is `metric_id + reference_date`; an identical
replay preserves prior lineage, while a changed value for an existing key
fails explicitly. Evidence identity is `evidence_id`; identical replays are
safe and conflicting content for the same ID fails. DuckDB read helpers query
the two Gold datasets without mixing derived rows into Macro Silver.

This boundary keeps official facts and deterministic calculations auditable
without asserting that macroeconomic movement causes changes in MercadoLibre
or Mercado Pago behavior. Product interpretation, hypothesis formation, and
recommendations require later explicit stages and evidence.


## Numeric transport and future acquisition (Sprint 8E.2B)

Macro observations now retain required `value` (float64), `unit` and `frequency`
from their source fact or analytic. Identity includes those values and the
`macro-numeric-v2` discriminator, preventing rounded claim text from conflating
numeric observations. Macro Evidence persistence schema is version 2; the Macro
Analytics schema remains version 1. Legacy Macro Evidence files require a
separately reviewed rebuild: the reader rejects the old schema, and no automatic
migration or append into a legacy generation occurs in this sprint.

The strategic macro adapter recomputes analytics from validated local Silver,
requires a stable series/source/unit/frequency per metric, preserves the source
URL and series in raw observations, and exposes calculation edges to exact source
periods. Its source and derived namespaces also bind IDs to series provenance and
operand IDs. These strategic Registry IDs are a separate contract from the
standalone macro observations; do not mix the two generations implicitly.

Acquisition is not performed by this adapter. Existing Python pipeline entrypoints
(no dedicated macro CLI was found) are:

| Module under meli_intelligence.pipelines | Function | Series |
|---|---|---|
| macro_bcb | build_bcb_selic_silver | Target/effective Selic |
| macro_ibge | build_ibge_ipca_silver | Monthly/12-month IPCA |
| macro_bcb_fx | build_bcb_usd_brl_silver | USD/BRL |
| macro_bcb_credit | build_bcb_credit_silver | Household credit and >90-day NPL |
| macro_bcb_activity | build_bcb_activity_silver | IBC-Br activity |
| macro_ibge_economy | build_ibge_economy_silver | Unemployment and retail |
| macro_bcb_pix | build_bcb_pix_silver | Monthly Pix count/value |

For a separately authorized acquisition, call the selected function from Python
with explicit start_date/end_date and controlled bronze_dir/output_path, e.g.:

```python
from datetime import date
from pathlib import Path
from meli_intelligence.pipelines.macro_bcb import build_bcb_selic_silver

# Future acquisition only: this call uses network and writes Bronze/Silver.
build_bcb_selic_silver(
    date(2023, 1, 1), date(2024, 12, 31),
    bronze_dir=Path("staging/bronze/bcb"),
    output_path=Path("staging/silver/macro_indicators.parquet"),
)
```

The existing macro_analytics.build_macro_gold writes final datasets and must not
be used for an in-memory preview. Use build_macro_analytics,
build_macro_observations or adapt_macro_strategic_evidence for local validation.
No acquisition, Gold materialization or migration was executed in 8E.2B.
