# Product Evidence Storytelling

## Purpose and audience

The Product Evidence page answers: “What evidence-backed hypotheses and
discovery questions currently exist around ecosystem engagement, and what
remains unknown?” It is for readers examining the persisted discovery record.
It stops at discovery and does not prescribe a Product direction.

## Source dataset and actual schema

The page reads the catalogued `product_evidence` Gold dataset through the
existing `ui.data.load_dataset` read path and Product Evidence query module.
It does not call a builder, source client, ingestion pipeline, or write API.

The inspected storage contract has these columns, in order:

`product_evidence_id`, `product_evidence_type`, `discovery_theme`,
`business_domain`, `reference_date`, `period_start`, `period_end`,
`period_type`, `entity`, `statement`, `rationale`, `source_evidence_ids`,
`source_interpretation_ids`, `source_pestel_ids`, `source_swot_ids`,
`source_hypothesis_ids`, `source_metric_ids`, `source`,
`methodology_version`, `definition_context`, and `scope`.

The type field is `product_evidence_type`; the record identity is
`product_evidence_id`; the user-facing text is `statement`; the persisted
theme is `discovery_theme`; the domain is `business_domain` (currently
`Ecosystem`); and business freshness is based on `reference_date`. The
persisted theme allowlist currently contains only `ECOSYSTEM_ENGAGEMENT`.
Lineage arrays are stored as JSON-encoded strings in Parquet. Definition and
version context remain available in `definition_context` and
`methodology_version`. Source, scope, entity and period bounds/type are also
preserved. The UI does not invent additional fields or themes.

The related Evidence registry uses the common model fields including
`evidence_id`, `evidence_type`, `business_domain`, `metric_id`,
`reference_date`, `claim`, and `source`. Its only supported labels are `FACT`,
`OBSERVATION`, and `INTERPRETATION`.

## Summary, ordering and filters

Summary contains only persisted hypothesis count, persisted discovery
question count, and latest filtered `reference_date`. If the dataset is
missing or unreadable, counts remain unavailable rather than becoming zero.
An available empty dataset can report zero rows. The summary has no readiness,
confidence, opportunity, quality, or engagement score.

Records are ordered by `reference_date` descending, then stable
`product_evidence_id` ascending. The page initially shows at most three
hypotheses and five discovery questions; remaining persisted records are
available in secondary sections. Date filters reuse `FilterState` and apply
to `reference_date`. A business-domain filter is not shown because Product
Evidence is explicitly cross-domain. No theme filter is
shown while there is only one persisted theme.

## Hypotheses and discovery questions

Only records whose persisted `product_evidence_type` is `HYPOTHESIS` appear in
the hypothesis section. Only `QUESTION_FOR_PRODUCT_DISCOVERY` records appear
in the question section. Unsupported types fail validation in the pure
presentation helper. Statements are shown as persisted, with their original
uncertainty and meaning; questions remain open and are not answered by the
page.

## Evidence and strategy lineage

Each Product record retains its persisted Evidence IDs, Interpretation IDs,
PESTEL IDs, SWOT IDs, metric IDs, source, methodology version and definition
context in a details section. The Evidence registry is loaded only when the
reader requests linked source Evidence. The helper selects records only by
IDs explicitly listed in the selected Product rows' `source_evidence_ids`.
It does not infer support, expand relationships, or treat absent lineage as
support. Where records are available, `FACT`, `OBSERVATION` and
`INTERPRETATION` type labels and source metadata are preserved.

## Aggregate-data limitation and what remains unknown

Buyers, Fintech MAU, GMV, TPV, AUM and credit are aggregated measures. On
their own they do not establish that the same people use Commerce and
Fintech, individual cross-domain overlap, retention, activity frequency,
cross-sell, causality between domains, or an ecosystem-user count. The UI does
not estimate overlap, create a synthetic ecosystem-user count, or calculate
an engagement score. These limits explain what remains unknown without
creating a new Product problem, research plan, or discovery question.

## No causal inference or product solutioning

The conceptual chain remains FACT → OBSERVATION → INTERPRETATION → PESTEL /
SWOT → HYPOTHESIS → QUESTION_FOR_PRODUCT_DISCOVERY. The page starts from the
persisted Product Evidence layer and creates none of those records at
runtime. A hypothesis is not a fact or conclusion; a discovery question is
not an answer, recommendation, feature, roadmap, experiment, or solution.
No causal claims are generated.

## Progressive disclosure, Nielsen and accessibility

The first view contains context, data status, latest reference date and two
persisted counts. Hypotheses and questions follow; additional records,
lineage, definition context and supporting Evidence are available on demand.
The page uses textual labels for Hypothesis and Question for Product
Discovery, clear headings, readable source/date context and explicit missing,
empty or invalid states. Category meaning and status do not depend on color or
emoji. This supports visibility of system status, recognition over recall,
user control through date filters, error recovery and a minimalist hierarchy.

## Degraded states

The page remains renderable when `product_evidence` is MISSING, EMPTY or
INVALID, and when `evidence_registry` or linked supporting Evidence is
unavailable. It displays an explicit availability or limitation message;
missing data never becomes zero and no synthetic records are created. The
Data Quality & Sources page remains the reference for technical diagnosis.
