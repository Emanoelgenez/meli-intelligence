# Financial Analytics Methodology

## Scope

This layer derives fundamental financial analytics from the canonical
SEC Silver dataset.

It does not use stock prices, MELI34 data, Product metrics, or market
valuation data.

## Revenue denominator

Margins use:

`net_revenues_financial_income`

Source concept:

`us-gaap:Revenues`

This represents the consolidated top-line definition selected for the
current MercadoLibre reporting structure.

## YoY growth

Formula:

`(current_value / previous_year_value - 1) * 100`

Comparison is only performed between periods with the same:

- period type;
- period label;
- relative fiscal year position.

Examples:

- Q1 versus Q1;
- Q2 versus Q2;
- H1 versus H1;
- 9M versus 9M;
- FY versus FY.

Growth is not calculated when the previous-year value is zero or
negative because the resulting percentage is not considered
analytically comparable in V1.

## Margins

Gross margin:

`gross_profit / net_revenues_financial_income`

Operating margin:

`operating_income / net_revenues_financial_income`

Net margin:

`net_income / net_revenues_financial_income`

Operating cash flow margin:

`operating_cash_flow / net_revenues_financial_income`

All percentage results are multiplied by 100.

Only exact matching economic periods are joined.

## CAPEX

The canonical V1 analytics metric `capex` uses only:

`capex_productive_assets`

Source concept:

`us-gaap:PaymentsToAcquireProductiveAssets`

The historical legacy concept:

`us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`

is intentionally not blended automatically into the V1 CAPEX series.

The current `PaymentsToAcquireProductiveAssets` concept is available
for MercadoLibre annual periods beginning in 2022 in the current SEC
Company Facts history.

Subannual observations using this concept are available from 2024 in
the current dataset.

Therefore:

- annual CAPEX/FCF may be calculated from 2022 onward when the
  ProductiveAssets fact is present;
- quarterly and YTD CAPEX/FCF are only calculated for periods where the
  ProductiveAssets fact is explicitly reported;
- the legacy PPE concept remains available in Silver for lineage and
  audit purposes but is never used as an automatic fallback.

No values are synthesized to bridge gaps between the two concepts.

## Free Cash Flow

Formula:

`operating_cash_flow - capex_productive_assets`

CAPEX is stored as a positive cash-outflow magnitude, therefore it is
subtracted from operating cash flow.

FCF is calculated only when both source metrics exist for the exact
same reported economic period.

No quarter is derived from YTD values in this version.

In particular, Q4 is not generated as:

`FY - 9M`

That may be added later as an explicitly derived fact with separate
quality controls.

## Free Cash Flow Margin

Formula:

`free_cash_flow / net_revenues_financial_income * 100`

Again, all source facts must refer to the exact same economic period.

## Methodological principle

A derived analytical metric must never be confused with a source fact.

Every analytical row records:

- formula;
- source metrics;
- whether it is derived;
- methodology version.