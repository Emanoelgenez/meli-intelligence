# Macro Brasil — BCB household free credit and delinquency

## Scope and source

This slice uses BCB SGS monthly series 20570 and 21112, deliberately restricted to the same population and product scope: free-market credit operations to individuals, total. Series 20570 is the end-of-period outstanding balance, in millions of BRL, and excludes directed credit. Series 21112 is the percentage of that free-credit portfolio with at least one installment overdue by more than 90 days. Both are reported indicators in the `Macro` domain.

The pipeline requests only SGS `(20570, 21112)`. It reuses the BCB client and its bounded date chunking, immutable BCB Bronze storage, generic SGS transformer, shared macro Silver, and DuckDB query layer. Bronze preserves the original BCB dates and bytes. For registered `monthly` BCB series, transformation maps the observation to the last calendar day of its month (`01/02/2024` becomes `2024-02-29`); `daily` observations retain their original dates. This is an analytical period convention and does not modify Bronze.

Rows are stored in the same `macro_indicators.parquet`, with source identities `bcb_sgs:20570` and `bcb_sgs:21112`. The economic key remains `metric_id + reference_date`. Identical repeated values preserve existing lineage; a changed value for an existing key raises a conflict for manual review instead of silently replacing history.

## BCB delinquency versus MercadoLibre NPL

BCB series 21112 measures delinquency **over 90 days** for free-market credit to individuals. MELI's `npl_15_90_total` covers **15–90 days** for MercadoLibre's total credit portfolio. These indicators have different delinquency windows and portfolio scopes and are not directly comparable. Do not calculate a spread between them or treat one as explaining the other. They may only serve as distinct contextual signals of credit quality.

## Limits

These are macro context observations, not causal explanations of MercadoLibre behavior or outcomes. This slice does not compute growth derivatives, correlations, regressions or a macro credit score.
