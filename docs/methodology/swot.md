# SWOT Evidence Mapping

## Objective and layers

SWOT is a conservative strategic classification of existing Evidence. It consumes the common Evidence Registry and, for external context, the PESTEL dataset. The layers remain distinct: Evidence preserves sourced facts, observations, and interpretations; PESTEL classifies external context; SWOT classifies eligible internal performance or external context. SWOT adds no source facts.

Each output preserves the source `claim` verbatim and puts the rule-based assessment in a separate `assessment` field. Every row is explicitly marked `is_interpretation = True`; source Evidence types remain in `source_evidence_types`.

## INTERNAL and EXTERNAL

The explicit internal domains are Financial, Commerce, Fintech, Ecosystem, Ads, and Logistics. Internal classifications can only be STRENGTH or WEAKNESS and require an allowlisted metric, its matching business domain, a finite numeric value, and an allowed direction/claim kind.

Macro and other non-company domains are external. OPPORTUNITY and THREAT require a matching PESTEL row, matching metric lineage, and compatible Evidence lineage. No macro signal can become an internal Strength or Weakness, and no company metric can become an external Opportunity or Threat.

## Allowlisted rules

Internal YoY growth rules cover reported revenue, net revenue plus financial income, GMV, active buyers, Fintech MAU, and TPV. Positive growth with a positive value can be classified as STRENGTH; an explicitly negative YoY change with a negative value can be classified as WEAKNESS. Other metrics and mismatched domains are omitted.

External rules are intentionally narrow: positive Pix transaction-count YoY may be classified as OPPORTUNITY only through a TECHNOLOGICAL PESTEL record explicitly tagged for digital payment adoption; a positive Selic change may be classified as THREAT only through its matching ECONOMIC PESTEL record. These labels describe the external context and do not assert company impact. Other evidence is omitted unless a future methodology version adds a specific rule. Positive or negative sign alone never determines category.

## Lineage and compatibility

`source_evidence_ids` must resolve in the supplied Evidence Registry. External rows also preserve `source_pestel_ids` and `source_pestel_dimensions`; each referenced PESTEL item must exist and its complete Evidence lineage must be included. Internal rows must have no PESTEL lineage. Scope mixing, unknown IDs, metric mismatches, incompatible reference dates/periods, and conflicting explicit definition tokens fail validation.

`swot_id` is a deterministic SHA-256 of category, claim, assessment, Evidence IDs, PESTEL IDs, and reference date. Output ordering is deterministic. Storage uses a dedicated Gold Parquet file with a fixed Arrow schema, ZSTD compression, atomic replacement, idempotent replay, and conflict failure. Query filters validate category before filesystem access.

## Guardrails and limits

Claims, assessments, and rationales are checked for explicit causal or prescriptive language. SWOT is not causal inference, a Product problem statement, a recommendation, or a Product solution. It does not create hypotheses, features, roadmap items, RICE/ICE scores, or prioritization. Correlation is not causality.

No forced coverage is required: any category may be empty. In particular, the current allowlist can yield no Weakness, Opportunity, or Threat for a dataset. Missing classifications are preferable to fabricated completion of a 2x2 matrix.

BCB household credit NPL measures delinquency above 90 days and is never treated as MercadoLibre's `npl_15_90_total`, which covers 15–90 days. The BCB metric is external macro context and is not eligible as an internal weakness.
