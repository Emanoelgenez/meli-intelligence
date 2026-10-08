# Brazil activity, employment and retail indicators

This slice adds three reported macro observations to the shared macro
indicator store. The data provide economic context; they do not establish
causal effects on MercadoLibre or its users.

## BCB IBC-Br

SGS 24364 is the seasonally adjusted Banco Central Economic Activity Index
(IBC-Br). The adjusted series is used as a monthly conjunctural activity
signal. IBC-Br is an activity indicator and is not Brazil's official GDP
measure. This pipeline reports its levels only and does not derive growth.
Monthly SGS dates are normalized in Silver to the last calendar day of the
reference month; the original response remains in BCB Bronze.

## PNAD Contínua unemployment

SIDRA table 6381, variable 4099, reports the unemployment rate for people
aged 14 or older. Each estimate covers a rolling three-month window and is
published monthly. The frequency is recorded as `rolling_3m_monthly`, not as
a simple monthly observation. Silver `reference_date` is the last calendar
day of the terminal month. For example, 2023-12-31 identifies the
October-November-December 2023 window; it is not an instantaneous observation.

The parser validates the variable label and obtains the period dimension from
the SIDRA header. The requested SIDRA IDs could not be independently queried
in the restricted network environment during implementation. A mismatch in
the official payload's semantic label therefore fails explicitly at runtime.

## Retail sales volume

SIDRA table 8880, variable 11708, reports the seasonally adjusted
month-over-month PMC variation. The registry applies a semantic filter using
the header-described “Tipos de índice” dimension and keeps only “Índice de
volume de vendas no comércio varejista”. The nominal sales revenue index is
excluded. No SIDRA classification code is assumed by the implementation.

The parser discovers the classification dimension by its header label,
requires the requested category to exist unambiguously, filters it before
checking the economic key, and then requires one row per `metric_id` and
`reference_date`.

## Storage and revisions

Raw SIDRA and SGS responses are retained in their existing immutable Bronze
stores. The normalized observations share `macro_indicators.parquet`, with
source-qualified series identities. The existing merge policy preserves
lineage for identical key/value repeats and stops on a changed value so an
official historical revision can be reviewed. Seasonally adjusted activity
and retail histories may be revised by their publishers.

No growth rates, correlations, regressions, product interpretations, or
causal claims are produced here.
