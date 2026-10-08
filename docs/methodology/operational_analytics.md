# Operational Analytics Methodology

## Scope

Operational analytics are derived only from canonical Operational
Silver facts sourced from MercadoLibre earnings releases filed with
the SEC.

No stock-price information is used.

## Definition compatibility

A year-over-year comparison requires:

- the same metric;
- the same period type;
- the same period label;
- the same calendar shape;
- a compatible metric definition.

Definition changes are not silently bridged.

### Buyers, GMV and items sold

The definitions change from Q2 2025 when food delivery is incorporated.

`v1_marketplace_only` and `v2_food_delivery` are not treated as
comparable definitions.

H1, 9M and FY 2025 begin before the Q2 2025 definition change.
They are therefore classified as:

`v2_food_delivery_transition_2025`

Transition periods are preserved as reported but are not treated as
comparable with either a fully pre-change or fully post-change
accumulated period.

Quarterly Q2 2025 onward observations use `v2_food_delivery`.

### Fintech MAU

The definition changes from Q1 2026.

The old and new definitions are not bridged automatically.

### TPV and payment transactions

`v2_excludes_p2p` and `v2_recast_excludes_p2p` are treated as one
comparison family because the latter identifies historical values
explicitly recast under the exclusion-of-P2P methodology.

The raw publication version remains preserved in Silver.

## YoY growth

Formula:

`(current_value / previous_year_value - 1) * 100`

For currency metrics this is growth in the reported USD value.

It is not the company's FX-neutral growth rate.

## NIMAL

NIMAL is already a percentage.

Its YoY movement is therefore represented as:

`current_nimal - previous_year_nimal`

and expressed in percentage points.

## Items per buyer

Formula:

`items_sold / unique_active_buyers`

This is an analytical engagement/intensity proxy and not a
company-reported KPI.

## GMV per buyer

Formula:

`gmv / unique_active_buyers`

It uses reported USD GMV.

It is an analytical commerce-intensity proxy and is not a
company-reported KPI.

## Acquiring TPV share

Formula:

`acquiring_tpv / tpv * 100`

This is a mix metric. A higher value is not automatically interpreted
as economically better.

## No synthetic ecosystem index

V1 does not combine Commerce and Fintech metrics into a synthetic
ecosystem engagement score.

Cross-domain conclusions must remain evidence-based and explicitly
separate facts, observations, interpretations and hypotheses.