# Evidence Synthesis Methodology

Sprint 4A provides a shared, auditable representation for reported facts and observations, plus a narrow deterministic interpretation layer.

## Evidence stages

- FACT is a normalized reported source fact. Its claim retains the source statement or reported value.
- OBSERVATION is a factual description grounded in a source fact or an approved deterministic analytical output. It is not an explanation.
- INTERPRETATION is an explicitly labeled, rule-based reading of one or more observations. It is never stored as FACT and always carries source Evidence IDs.

This sprint stops at INTERPRETATION. It does not produce hypotheses, product discovery questions, recommendations, solutions, features, or prioritization.

## Common schema and provenance

The common record carries Evidence ID/type, business domain, entity and metric, reference/period dates, value/unit/frequency when available, claim and claim kind, source, source metric, source Evidence IDs, interpretation flag, methodology version, and definition context.

Operational source IDs are preserved when supplied. The existing macro OBSERVATION IDs remain unchanged and are never relabeled as FACT. Financial adapters normalize only source facts or financial analytics that already exist; they do not calculate new metrics. Evidence ID collisions across inputs fail explicitly.

Interpretation IDs use SHA-256 over the interpretation type, domain, metric, reference date, claim, and sorted source IDs. A changed claim or changed lineage therefore changes the ID. Each interpretation must cite at least one known Evidence ID; unknown references fail validation.

## Deterministic rules and compatibility

V1 allowlists only positive reported revenue growth, positive GMV growth, positive Fintech MAU growth, positive Pix transaction-count YoY growth, and a declining Selic target. Other observations do not automatically produce interpretations. The statements are deliberately narrow and describe only what the selected data reports.

The only multi-evidence rule currently enabled is the explicit Fintech MAU plus TPV growth pair. Both observations must share a reference date, period type/label when provided, business domain, and exact definition context. Incompatible periods or definitions fail rather than being treated as comparable.

The BCB household credit delinquency measure is for more than 90 days overdue. MercadoLibre npl_15_90_total covers 15–90 days. They are different definitions and are not directly compared or combined.

A source definition/version is carried in definition_context when provided. This preserves known operational changes such as TPV/payment-transaction reporting that excludes P2P in the v2 comparison family. The multi-source rule requires exact context equality, which conservatively blocks known definition changes and any uncertain comparability.

## Guardrails and scope

A simple explicit language guard rejects obvious causal or prescriptive wording in English and Portuguese. Correlation is not causation. An interpretation is not a hypothesis or recommendation. Product solutioning and prioritization belong to later discovery work and are outside this data layer.

## Gold persistence and query

The common registry and interpretations are separate Gold Parquet datasets with a fixed Arrow schema, ZSTD compression, atomic replacement, and replay-safe conflict checks. Exact replay preserves the stored record; a reused Evidence ID with different content raises an error. DuckDB reads support Evidence type, business domain, metric, date-range, and source Evidence ID filters.


## Financial identity revision (Sprint 8E.2A)

Financial rows with a non-null, non-blank explicit `evidence_id` retain that ID
(as text). Missing or blank IDs receive a SHA-256 identity whose canonical JSON
payload includes `identity_version="financial-v2"`. This identity version is
separate from the unchanged Evidence schema and strategic methodology versions.

The generated identity includes evidence type/domain, entity and CIK, metric,
reference date, both effective period boundaries, period type/label, numeric
value and unit, claim, and available SEC provenance: source/URL, accession,
filing date, Bronze reference/content hash, taxonomy, concept and form. Dates
are normalized to calendar dates before hashing; absent values, pandas NA/NaT
and NaN serialize as JSON null. Numeric values use the existing float64 value
contract. SEC `filed_at` fills the common `filing_date` when the latter is absent;
an explicitly supplied filing date takes precedence.

Identity is local to a row: input ordering, DataFrame index and other rows in a
batch do not affect it. The adapter does not append row counters, select a
preferred filing or drop duplicates. Repeated generated IDs and repeated
explicit IDs still fail common normalization. Cross-source collisions still
fail Registry construction. Raw facts, operational/macro IDs, evidence types,
strategic rules and Arrow columns are unchanged.

### Compatibility and proposed migration (not executed)

All automatically generated financial IDs change from the legacy hash of
(type, metric, final date, claim, source). Existing explicit IDs remain stable,
but filling a previously missing filing date can change the associated record
content and must not bypass persistence conflict checks. Consumers must not
append regenerated financial records to an old Registry: the storage key is
`evidence_id`, so this could retain both generations of the same fact.

Before a separately approved migration:

1. Inventory and snapshot the Registry and all dependent interpretations,
   PESTEL, SWOT, product evidence and any external references.
2. Rebuild identities from the complete, immutable Silver inputs in a separate
   staging location. Audit old-to-new mappings using entity, metric, both period
   boundaries and filing provenance. A colliding legacy ID can map to multiple
   new IDs; never choose one by row order or rewrite an ambiguous reference
   automatically.
3. Rebuild dependent lineage from source evidence, resolve ambiguous historical
   references explicitly, then validate counts, schemas, uniqueness and every
   referenced ID. Preserve source-explicit IDs and flag changed record content.
4. Review and promote the Registry and its dependents as a consistent generation,
   with a rollback snapshot. Do not mix legacy and financial-v2 materializations.

This sprint performs no migration or Gold materialization. A zero-classification
PESTEL/SWOT result remains valid when inputs do not meet the existing allowlists.


## Strategic preparation (Sprint 8E.2B)

`evidence.strategic.build_strategic_evidence(financial=..., operational_kpis=...,
operational=..., macro=...)` is a pure, local-input API. It returns a
`StrategicEvidence` containing `registry`, `lineage` and `omissions`. No source
client, writer or strategy builder is invoked. The three source-specific APIs
are `adapt_financial_strategic_evidence`, `adapt_operational_strategic_evidence`
and `adapt_macro_strategic_evidence`; they return the same contract.

Financial preparation preserves the existing financial Evidence identities and
all input facts, and uses the five existing financial YoY calculators. Only
revenue growth is currently eligible for internal SWOT. Operational preparation
handles the consolidated GMV, unique buyers, Fintech MAU and TPV families and
reuses their YoY calculator. Other operational metrics are explicitly listed in
omissions with their native period and accession; their Silver rows are untouched.
Operational reported KPI evidence is FACT; computed evidence is OBSERVATION.
Existing financial and operational-statement types/IDs remain unchanged. No
INTERPRETATION records are generated by these adapters.

Company operands must have source identity, entity, finite values, correct units
and valid native periods. Calculations are partitioned by entity and reject
ambiguous periods. Missing/nonpositive prior-year baselines and incompatible
calendar/definition pairs produce explicit omissions, not invented growth.
The operational calculator's existing comparison families are reused: only
`v2_excludes_p2p` and `v2_recast_excludes_p2p` may compare as one TPV family;
P2P-inclusive definitions are not mixed with that family. Segment/geographic
scope columns are rejected because this bridge targets consolidated Silver.
Qualifier-aware extended analytics are outside this bridge's metric scope.

### Calculation lineage versus contemporary strategic support

The unchanged SWOT validator requires common `source_evidence_ids` to refer to
compatible contemporary periods. A YoY calculation also needs the prior year.
Those are different relationships: `source_evidence_ids` records the current
supporting fact when it shares the observation date; the separate calculation
`lineage` records **all** operands at their original dates, with roles `current`
and `previous` (or only `current` for a snapshot). Prior facts are never redated.
A month-end FX snapshot whose source quote precedes month-end has no contemporary
support ID, but its calculation edge still identifies the exact daily quote.

`LINEAGE_SCHEMA` version 1 contains observation_id, source_evidence_id, role,
operation and optional source_series_id. Both IDs resolve in the same Registry.
`validate_derivation_lineage` checks coverage, roles, references, period/definition
compatibility, units/domains, series identity and recomputed numerical values.
Derived identity includes ordered operand identities; changed inputs cannot reuse
a derived ID merely because their percentage change is unchanged.

The Registry is not a complete calculation audit by itself. Any future Gold
promotion must persist and validate Registry **and calculation lineage together**.
Dropping the sidecar loses the previous-period relationship. This is an explicit
new contract for 8E.2C, not a relaxation of PESTEL/SWOT temporal validation.
Use normalize_evidence, validate_derivation_lineage, build_pestel,
validate_pestel_lineage, build_swot and validate_swot_lineage before promotion.

Macro growth does not imply technological adoption. Untagged positive Pix YoY
still classifies as ECONOMIC and may cause the unchanged SWOT builder to reject
missing TECHNOLOGICAL lineage. Keep that limitation visible; never add adoption
tags to force OPPORTUNITY coverage or silently suppress the failing evidence.
