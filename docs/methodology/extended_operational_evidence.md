# Extended Operational Evidence Methodology

## Structured extended KPIs

Only disclosures with sufficiently clear numeric meaning and scope are
promoted to structured KPI facts.

V1 includes:

- AUM;
- total credit portfolio;
- total-portfolio 15-90 day NPL.

All are modeled as quarter-end INSTANT observations.

Reported wording is preserved through `value_qualifier`.

Supported qualifiers include:

- `exact`;
- `approximate`;
- `lower_bound`.

An approximate or lower-bound disclosure must never be presented as a
more precise value than the company reported.

## NPL scope

The structured NPL metric is limited to the total credit portfolio.

Credit-card-specific NPL is not substituted for total-portfolio NPL.

A missing total-portfolio observation therefore remains missing.

## Evidence facts

MELI+, ecosystemic users, advertising and fulfillment/logistics are
stored as source-grounded evidence statements when recurring,
definition-consistent numeric series are not available.

Evidence rows are classified as `FACT`.

They are not automatically converted into observations,
interpretations, hypotheses or Product recommendations.

Those transformations belong to the later evidence methodology layer.

## Deterministic observations

Each evidence FACT can be normalized into exactly one OBSERVATION. V1
preserves the source statement and normalizes whitespace only. The
observation carries the original evidence ID, period and source lineage,
plus a deterministic observation ID and a business-domain tag. The ID is
the SHA-256 digest of the evidence ID.

The only stages implemented are FACT and OBSERVATION. This normalization
does not create interpretations, hypotheses, Product recommendations,
causal claims, engagement indexes, ecosystemic-user estimates or
artificial combinations of evidence types. A deterministic lexical
`claim_kind` is attached only for one unambiguous explicit signal; when
signals overlap or are unclear, it is `other`.

## Ecosystem engagement

No absolute ecosystemic-user count is estimated.

No synthetic ecosystem engagement index is created in V1.

Reported relative evidence such as YoY growth, per-user differences,
category breadth and cross-domain engagement may be stored as evidence
without implying causality.
