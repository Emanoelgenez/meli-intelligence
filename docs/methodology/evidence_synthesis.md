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
