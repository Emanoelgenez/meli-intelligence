# BCB Monthly Pix Statistics

## Source and scope

This slice uses the Banco Central do Brasil's **Estatísticas de Meios de
Pagamentos**, service `MPV_DadosAbertos`, FunctionImport
`MeiosdePagamentosMensalDA(AnoMes=@AnoMes)`. Its monthly Pix fields are
`quantidadePix` and `valorPix`. The monthly Pix source combines SPI settlements
and participant-reported settlements outside SPI, including information from
document 1201, as represented by the official aggregate dataset.

The request uses the official Olinda OData endpoint:

`https://olinda.bcb.gov.br/olinda/servico/MPV_DadosAbertos/versao/v1/odata/MeiosdePagamentosMensalDA(AnoMes=@AnoMes)`

with `@AnoMes='YYYYMM'`, `$format=json`, and `$select=AnoMes,quantidadePix,valorPix`.
The observed contract treats `AnoMes` as a lower bound: records may begin at
the requested month and continue through the latest available month. The
client validates that returned months do not precede the lower bound, follows
OData `nextLink` when present, and does not assume API ordering.

## Metrics and units

The endpoint already supplies one aggregate Pix row per month in these fields;
this pipeline does not sum or combine any dimensional cuts.

| Silver metric | Source field | Source unit | Normalization | Silver unit |
| --- | --- | --- | --- | --- |
| `pix_transactions_count_monthly` | `quantidadePix` | thousand transactions | `× 1,000` | `transactions` |
| `pix_transactions_value_monthly` | `valorPix` | million BRL | `× 1,000,000` | `brl` |

These source units and scale factors were confirmed by the profiling supplied
for this sprint against BCB published totals. Decimal arithmetic is used
before scaling; normalized transaction quantities must be integral. Values
must be finite and nonnegative.

`reference_date` is the last calendar day of `AnoMes`, including leap-year
February. It is an economic month-end, not the retrieval date.

## Bronze and Silver

Bronze preserves each raw HTTP response page byte-for-byte with independent
metadata, URL, retrieval time, page index, requested start month, and SHA-256.
Because the source treats the requested month as a lower bound, Bronze may
contain months later than the requested `end_date`. Silver is filtered locally
to `start_date <= reference_date <= end_date` and requires both Pix metrics in
the requested range. The resulting observations merge into the shared
`macro_indicators.parquet` under the existing economic key
`metric_id + reference_date`; source identity is carried in
`source_series_id` (`bcb_mpv:monthly:quantidadePix` or
`bcb_mpv:monthly:valorPix`).

## Revision safety and interpretation limits

Participant-reported transactions outside SPI may be revised retroactively.
An identical key and value retains its existing lineage. A changed value for
an existing key stops the pipeline with an explicit conflict for manual
review; this slice does not overwrite historical data silently.

### Why no dimensional aggregation is needed

`MeiosdePagamentosMensalDA` directly provides one monthly aggregate row with
`quantidadePix` and `valorPix`. The pipeline therefore does not sum rows across
PF/PJ, regions, initiation types, or other dimensions, avoiding double-counting
from overlapping views.

These macro observations describe national payment activity. They do not by
themselves establish a causal relationship with MercadoLibre or Mercado Pago
behavior.
