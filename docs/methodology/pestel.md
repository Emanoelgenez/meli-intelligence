# PESTEL Evidence Layer

## Objective

The PESTEL layer classifies records from the common Evidence Registry. It does not create facts or change claims. Each output is an auditable classification with direct Evidence lineage.

## Dimensions and coverage

Valid dimensions are POLITICAL, ECONOMIC, SOCIAL, TECHNOLOGICAL, ENVIRONMENTAL, and LEGAL. The dataset may contain only dimensions supported by explicit Evidence. Missing Political, Legal, or Environmental records remain absent; coverage is never fabricated.

V1 uses deterministic structured allowlists based on metric ID, business domain, claim kind, and definition context. It does not use an LLM, network calls, embeddings, or broad keyword matching.

- Macro indicators such as Selic, IPCA, USD/BRL, unemployment, IBC-Br, retail, household credit, delinquency, and national Pix transaction measures classify as ECONOMIC.
- Explicit Fintech MAU and unique active buyer metrics classify as SOCIAL only in their Fintech or Commerce domains. This describes reported adoption or aggregate usage and implies no individual behavior or cause.
- Pix remains ECONOMIC by default as a national payment activity measure. TECHNOLOGICAL requires an explicit technology-adoption claim kind and matching definition-context tag.
- POLITICAL, LEGAL, and ENVIRONMENTAL require structured claim kinds that explicitly identify public policy/government decisions, regulatory/compliance obligations, or environmental measurements. No such classification is inferred from a generic source or claim.

A record receives at most one dimension in V1.

## Evidence types and lineage

PESTEL accepts only FACT, OBSERVATION, and INTERPRETATION from the Sprint 4A common model. The original evidence type is preserved in source_evidence_types. For an interpretation, the PESTEL entry cites that interpretation and its upstream Evidence IDs. Every ID must exist in the supplied Evidence Registry; unknown IDs fail.

The claim text is copied without semantic rewriting. The record also carries the business domain, reference and period dates, source metrics, original sources, interpretation flag, and definition context.

## IDs and rationale

Each PESTEL ID is a SHA-256 hash of the dimension, unchanged claim, sorted Evidence IDs, and reference date. Replaying the same classification yields the same ID. A different dimension or lineage yields a different ID.

Each dimension has a fixed short classification rationale. The rationale describes why the record fits that dimension; it does not state an effect, recommendation, opportunity, threat, strength, weakness, or product solution.

## PESTEL is not causality or SWOT

PESTEL is a context classification, not causal analysis. A macro indicator classified ECONOMIC does not establish an effect on MercadoLibre. PESTEL also does not assign SWOT strengths, weaknesses, opportunities, or threats. It creates no hypothesis, product discovery question, recommendation, or solution.

## Storage and query

The output is written to data/gold/strategy/pestel.parquet with a fixed Arrow schema, ZSTD compression, atomic replacement, and replay/conflict checks. DuckDB queries filter by dimension, business domain, source metric, date range, and source Evidence ID.
