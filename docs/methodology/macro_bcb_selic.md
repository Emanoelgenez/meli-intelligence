# Macro Brasil: BCB SGS Selic Foundation

## Sprint 3A scope

This slice establishes a reusable official-source ingestion path for
exactly two required daily Selic series, SGS 432 and SGS 1178. The
pipeline fails without observations for either series. The source is the
Banco Central do Brasil's free SGS JSON API:

`https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_code}/dados`

| SGS code | Metric ID | Meaning | Unit |
| --- | --- | --- | --- |
| 432 | `selic_target_annual` | Meta Selic defined by Copom | `percent_per_year` |
| 1178 | `selic_effective_annual_252` | Effective one-business-day repo rate annualized on a 252-day basis | `percent_per_year` |

Meta Selic and effective Selic are separate series and are never
substituted for each other. Both are daily observations in a `Macro`
business domain, and neither is marked universally higher-is-better.

## Ingestion and lineage

The SGS client sends JSON requests with explicit `dataInicial` and
`dataFinal` filters in `DD/MM/YYYY`, validates the response shape, uses
an explicit timeout and raises HTTP or malformed-payload errors. Each
request is limited to ten calendar years. Longer ranges are split into
inclusive chunks ending conservatively at `start + 10 years - 1 day`;
the next chunk starts exactly one day after the previous end. This keeps
each inclusive request at or below the API limit without gaps or overlaps.

Bronze stores the original response bytes without semantic conversion.
Each chunk has a distinct JSON file and metadata sidecar recording
provider, dataset, series code and metric ID, request URL and requested
dates, retrieval time, ingestion version and payload SHA-256.

Transformation maps SGS `data` to `reference_date` and `valor` to a
finite numeric `value`. Invalid dates and values fail explicitly. The
generic typed Silver table is `data/silver/macro/macro_indicators.parquet`
and can host later macro series. It uses a stable Arrow schema, zstd
compression, deterministic ordering and atomic replacement. Its
economic key is `metric_id + reference_date`. Duplicate keys fail;
repeated identical observations retain the existing Silver lineage, and
conflicting values fail instead of overwriting historical values.

Silver rows retain metric and source-qualified series identifiers, unit, frequency, source,
request URL, retrieval timestamp and ingestion version. Bronze paths for
each newly ingested request are recorded in the Silver metadata sidecar.

## Limitations and interpretation

V1 ingests only Meta Selic and effective annualized Selic. It does not
calculate monthly averages, changes, interest-rate regimes or
relationships with MercadoLibre metrics. Future macro indicators belong
in the same generic registry and Silver table, but are outside this
slice.

Macro data provide economic context; they do not explain user behavior
causally. Any future correlation is not evidence of causality.

Macro Silver identifies each source series with the source-qualified string
`source_series_id` (for example, `bcb_sgs:432` and `bcb_sgs:1178`). The
economic key remains `metric_id + reference_date`.
