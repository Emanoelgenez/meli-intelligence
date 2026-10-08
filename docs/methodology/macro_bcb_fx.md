# Macro Brasil — BCB SGS USD/BRL selling rate

## Scope and meaning

This pipeline ingests BCB SGS series 1, **Taxa de câmbio - Livre - Dólar americano (venda) - diário**, as `usd_brl_sell_rate`. This is the official BCB daily selling exchange-rate series (PTAX). Each value is Brazilian reais per US dollar (`brl_per_usd`), at daily frequency. The series is an official BCB macroeconomic context measure. It is not an intraday quote or a trading signal, and a higher or lower exchange rate is not universally better.

## Ingestion and storage

The FX pipeline has fixed scope `(1,)`. It reuses the BCB SGS client, including its request chunking, immutable BCB Bronze storage, and generic SGS transformer. Bronze retains the original response and lineage metadata, including SGS code, metric ID, URL, requested dates, retrieval time, ingestion version and payload SHA-256.

Normalized records use `source_series_id = bcb_sgs:1` and are merged into the shared `macro_indicators.parquet` with Selic and IBGE IPCA. The economic key remains `metric_id + reference_date`. Identical repeated values preserve stored lineage; a different value for an existing key raises an explicit conflict for review rather than overwriting history.

## Analytical limits

The series is daily and does not provide an intraday path, bid/ask spread, OHLC, returns, forecast or trading signal. It is not used here for correlations, valuation adjustments or causal claims about MercadoLibre or its users.
