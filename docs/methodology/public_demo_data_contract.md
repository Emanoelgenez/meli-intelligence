# Public Demo Data Contrac

## Purpose

Define the persisted-data boundary for a first public portfolio application. This is a design contract, not an implemented public mode or authorization to publish source data. Audit baseline: `bd31e10f803c7f1d7cfe9d003459030b174dbe34`; reviewed on 2026-10-07. No production data was copied, transformed or published.

The [deployment audit](deployment_readiness.md) concluded `READY_WITH_FIXES`: clean-checkout startup works, but useful coverage and redistribution review remain unresolved. This contract reconciles its **14 datasets**, narrows the first bundle to two Company datasets, and keeps Market and optional domains explicitly unavailable. Existing Windows runtime evidence does not establish a tested Linux deployment.

## Principles

- Company facts, Market observations and Product evidence remain separate. MELI34 is a market instrument, never a Company fundamentals source.
- Source authority is not redistribution permission. These classifications are operational decisions, not legal opinions; no current provider terms were fetched in this audit.
- Prefer small transformed Silver snapshots over raw Bronze documents or response archives. Derived artifacts inherit relevant source dependencies.
- Preserve units, definitions, period types, revisions, provenance and nulls. Missing data is not zero. Correlation does not imply causation.
- Preserve `FACT → OBSERVATION → INTERPRETATION → PESTEL / SWOT → HYPOTHESIS → QUESTION_FOR_PRODUCT_DISCOVERY`. A Product hypothesis is not a validated Product problem. Do not generate strategic content to fill empty pages.
- Use immutable static releases and existing readers. No runtime ingestion, formula changes, financial-selection changes or new analytical claims.

## Dashboard dataset inventory

Authority: `ui/catalog.py`, `ui/data.py`, `ui/health.py`, page modules and their storytelling loaders; catalog defaults originate in storage modules. Paths below are repository-relative **local-mode** paths, not future public paths. “Operational domains” means Commerce, Fintech, Ecosystem, Ads and Logistics. “Unassigned” means the catalog has no domain tuple; do not invent one from the filename.

Every dataset participates in Executive Overview's health summary and Data Quality & Sources' health table and optional available-data preview. The consumers column lists additional **row consumers**, not just health reporting. All 14 are optional in today's catalog. “Essential” below is the proposed portfolio coverage requirement, not a change to today's runtime startup requirements.

| dataset_id | Display name | Domain | Layer | Expected local path | Row consumers beyond Data Quality | Behavior when missing | Essential for first bundle? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `evidence_registry` | Evidence registry | Unassigned | Gold | `data/gold/evidence/evidence_registry.parquet` | Product Evidence linked-evidence preview, when requested | Linked evidence unavailable; no replacement evidence | No |
| `extended_operational_evidence` | Extended operational evidence | Operational domains | Silver | `data/silver/sec/evidence_facts.parquet` | None | Health MISSING; no source preview | No |
| `extended_operational_kpis` | Extended operational KPIs | Operational domains | Silver | `data/silver/sec/extended_operational_kpis.parquet` | Fintech | Extended credit/risk measures missing; core Fintech can still render | No |
| `financial_facts` | Financial facts | Financial | Silver | `data/silver/sec/financial_facts.parquet` | Executive, Financial; Market valuation input | Financial facts/trend unavailable; no fabricated denominator | **Yes** |
| `interpretations` | Interpretations | Unassigned | Gold | `data/gold/evidence/interpretations.parquet` | Executive, Financial, Commerce, Fintech, Macro | Interpretation sections unavailable; factual displays remain possible | No |
| `macro_analytics` | Macro analytics | Macro | Gold | `data/gold/macro/macro_analytics.parquet` | Macro | Derived macro measures unavailable | No |
| `macro_evidence` | Macro observations | Macro | Gold | `data/gold/macro/macro_evidence.parquet` | Macro | Observations unavailable; none synthesized | No |
| `macro_indicators` | Macro indicators | Macro | Silver | `data/silver/macro/macro_indicators.parquet` | Executive, Macro | Macro snapshots/trends missing, never zero-filled | No |
| `market_capitalization` | Market capitalization | Market | Gold | `data/gold/market/market_capitalization.parquet` | Market valuation | Market cap and dependent valuation unavailable | No |
| `market_prices` | Market prices | Market | Silver | `data/silver/market/market_prices.parquet` | Market | Price/history unavailable | No |
| `operational_kpis` | Operational KPIs | Operational domains | Silver | `data/silver/sec/operational_kpis.parquet` | Executive, Commerce, Fintech | Operational snapshots/trends missing | **Yes** |
| `pestel` | PESTEL classifications | Unassigned | Gold | `data/gold/strategy/pestel.parquet` | Executive, PESTEL | No invented classifications | No |
| `product_evidence` | Product Evidence | Ecosystem | Gold | `data/gold/product/product_evidence.parquet` | Executive, Product Evidence | Explicit missing hypotheses/questions; no opportunities synthesized | No |
| `swot` | SWOT classifications | Unassigned | Gold | `data/gold/strategy/swot.parquet` | Executive, SWOT | No invented quadrant content | No |

Missing paths raise `FileNotFoundError` in the shared loader; health checks classify them `MISSING`, and page loaders guard or handle missing data. Readable empty files are `EMPTY`; unreadable files are `INVALID`. None is equivalent to `AVAILABLE`. Pages can initialize with all datasets missing, as tested in Sprint 8B; that is distinct from useful coverage.

The clean worktree contains only `data/bronze/.gitkeep`, `data/silver/.gitkeep` and `data/gold/.gitkeep`. Main's inventory contains 39 files including those placeholders. Path/footer/schema inspection identifies six present catalog datasets: financial facts (812 rows), operational KPIs (144), extended operational KPIs (18), extended operational evidence (52), Market prices (101), Market capitalization (101). The other eight catalog datasets are absent. Footer counts do not establish eligible metric/period coverage or publication permission. No production row contents were needed for this contract.

`data/silver/company/shares_outstanding.parquet` is an upstream Market Cap input, not a fifteenth catalog dataset. Raw SEC/Company payloads, Twelve Data responses and write-side metadata are likewise outside the dashboard inventory. BCB/IBGE support in the code does not imply persisted Macro artifacts exist in this inventory.

## Dataset classification

`PUBLIC_STATIC_CANDIDATE` means reviewed as eligible for proposed static packaging, without a blanket legal warranty. `TERMS_REVIEW_REQUIRED` means desirable for the first bundle but unresolved source/attribution review blocks publication. `EXCLUDE_FROM_PUBLIC_DEMO` is a deny decision. `OPTIONAL_MISSING_OK` means deliberately not selected for this release; it does not grant permission to publish later.

| dataset_id | Exactly one classification | Basis / release decision |
| --- | --- | --- |
| `evidence_registry` | OPTIONAL_MISSING_OK | Not persisted locally; no evidence registry needs to be manufactured for the core factual demo. Future inclusion requires complete approved lineage. |
| `extended_operational_evidence` | OPTIONAL_MISSING_OK | Present Company/SEC release-derived evidence, but no core narrative page requires it. Embedded text and upstream rights need review before later inclusion. |
| `extended_operational_kpis` | OPTIONAL_MISSING_OK | Present authoritative release-derived measures; useful Fintech extras, not required for MAU/TPV coverage. Omit to minimize the bundle; review sources before expansion. |
| `financial_facts` | TERMS_REVIEW_REQUIRED | SEC Company Facts reflecting Company filings; transformed numerical snapshot is preferred, but repository evidence does not document public redistribution/attribution clearance. |
| `interpretations` | OPTIONAL_MISSING_OK | Not persisted; project synthesis cannot be invented or detached from source evidence. |
| `macro_analytics` | OPTIONAL_MISSING_OK | Not persisted; derived BCB/IBGE context is outside first-release coverage. |
| `macro_evidence` | OPTIONAL_MISSING_OK | Not persisted; no observations generated for presentation completeness. |
| `macro_indicators` | OPTIONAL_MISSING_OK | BCB and IBGE/SIDRA source families are supported, but no local catalog artifact is present or selected. Any later snapshot needs source review. |
| `market_capitalization` | EXCLUDE_FROM_PUBLIC_DEMO | Existing persisted Gold depends on Twelve Data prices; derivation does not remove the restricted dependency. |
| `market_prices` | EXCLUDE_FROM_PUBLIC_DEMO | Twelve Data observations; public redistribution permission is not established. |
| `operational_kpis` | TERMS_REVIEW_REQUIRED | MercadoLibre operational releases/filing exhibits via SEC/Company sources; retain a small numerical Silver snapshot only after review of terms and required attribution. |
| `pestel` | OPTIONAL_MISSING_OK | Not persisted; no strategic classifications invented. |
| `product_evidence` | OPTIONAL_MISSING_OK | Not persisted; missing discovery hypotheses remain missing. |
| `swot` | OPTIONAL_MISSING_OK | Not persisted; no strategic quadrants filled artificially. |

Reconciliation: **0 PUBLIC_STATIC_CANDIDATE + 2 TERMS_REVIEW_REQUIRED + 2 EXCLUDE_FROM_PUBLIC_DEMO + 10 OPTIONAL_MISSING_OK = 14**. No classification category must be populated merely for symmetry. Later clearance requires an explicit contract/release review, not automatic promotion at runtime.

## Market exclusion policy

Exclude both `market_prices` and `market_capitalization`, including raw provider responses, transformed prices and price-dependent Gold. Do not ship upstream shares merely to rebuild excluded Market Cap. Do not disguise restricted observations as synthetic, move them to external hosting to evade review, or load ignored local/stale data.

Market remains navigable with an explicit “Unavailable in this public demo: market-price redistribution has not been cleared” explanation. This is a policy reason alongside existing availability states, not a new analytical result. No price history, price-derived Market Cap or price-dependent valuation multiple is displayed. Company facts may remain available independently.

No UI calculation replaces the backend valuation snapshot. P/B requires eligible authoritative book value and an allowed market numerator; excluding that numerator prevents a numeric multiple. P/S and P/Operating Cash Flow remain unavailable without valid TTM contracts; P/E remains outside scope. No Buy/Sell/Hold, target price, fair-value or trading recommendation is introduced. Market prices never explain Product/user behavior.

Reconsider exclusion only with documented permission covering the intended distribution or a separately cleared price source and explicit dependency/contract review. Neither is part of this sprint or a default Sprint 8D task.

## Minimal useful public bundle

The proposed dataset allowlist is exactly **`financial_facts` and `operational_kpis`**, conditional on source review. It provides factual Executive signals, Financial snapshots/history, Commerce GMV/activity, Fintech MAU/TPV and Data Quality source/date inspection. It does not promise complete Fintech credit/risk coverage or strategic interpretations.

Select a coherent window of up to four completed common quarters at a declared cutoff from already persisted, reviewed inputs. Require at least two comparable quarterly observations for `net_revenues_financial_income`, `gmv` and `tpv`, plus an eligible `fintech_mau` snapshot. Preserve existing definition boundaries; do not force comparisons across incompatible versions. Include existing eligible primary Financial facts (`operating_income`, `net_income`, `operating_cash_flow`) within that window where present; missing facts retain their current explicit states. Additional existing Financial/Commerce measures are optional within the two approved files, must be enumerated in the release manifest and must pass source review.

This is a coverage acceptance requirement, not a claim proven by footer row counts. Sprint 8D must inspect approved rows and execute existing selectors. If eligible coverage is insufficient, report the gap and revise the reviewed selection; do not calculate missing quarters, change financial selection or fabricate observations. Do not generate interpretations, Product Evidence, PESTEL or SWOT.

## Artifact schemas and paths

Proposed tracked files, **not created in Sprint 8C**:

| dataset_id / artifact | Exact proposed path | Format / reader | Metadata requirement |
| --- | --- | --- | --- |
| `financial_facts` | `demo_data/v1/silver/sec/financial_facts.parquet` | Existing `query.duckdb.query_financial_facts(parquet_path=...)`, unchanged | Release manifest required; production writer sidecar not needed by reader |
| `operational_kpis` | `demo_data/v1/silver/sec/operational_kpis.parquet` | Existing `query.operational.query_operational_kpis(parquet_path=...)`, unchanged | Release manifest required; production writer sidecar not needed by reader |
| Release manifest, not a catalog dataset | `demo_data/v1/manifest.json` | UTF-8 JSON; future public-mode validation, not an analytical reader | Required for publication and bundle validation |

Use the existing PyArrow schemas in `storage/silver.py` and `storage/operational_silver.py`, each version `1`. Retain every schema column, including nullable provenance/revision columns; do not replace typed dates or numbers with formatted strings. These grouped lists specify all fields; schema order and nullability follow the existing constants.

### Financial facts: 26 columns

| Type / nullability | Required columns |
| --- | --- |
| string, non-null | `entity_cik`, `entity_name`, `source`, `metric_id`, `taxonomy`, `concept`, `unit`, `period_type`, `period_label`, `form`, `accession_number` |
| int64, non-null | `value` |
| date32, nullable | `period_start`, `first_filed_at` |
| date32, non-null | `period_end`, `filed_at` |
| int32, non-null | `reference_year`, `occurrences` |
| string, nullable | `frame`, `source_fp`, `first_accession_number` |
| int32, nullable | `source_fy` |
| int64, nullable | `first_reported_value`, `value_change` |
| bool, non-null | `has_value_change`, `is_derived` |

`period_end` is the observation reference date; `filed_at` is disclosure time, not a substitute. Preserve QUARTER/YTD/FY/INSTANT distinctions and source/revision flags. Subset persisted rows without converting YTD/FY into quarters. The existing Financial selector continues determining eligibility. This schema has no `source_url`, Bronze path or content-hash column: do not invent them inside the Parquet file; record supplementary source references in the manifest.

### Operational KPIs: 29 columns

| Type / nullability | Required columns |
| --- | --- |
| string, non-null | `entity_cik`, `entity_name`, `source`, `metric_id`, `source_label`, `reported_scale`, `unit`, `period_type`, `period_label`, `definition_version`, `accession_number`, `source_url`, `source_bronze_file`, `source_content_sha256`, `first_accession_number` |
| float64, non-null | `reported_value`, `value`, `first_reported_value`, `value_change` |
| date32, nullable | `period_start`, `sec_report_date` |
| date32, non-null | `period_end`, `release_reference_period`, `filing_date`, `first_filing_date` |
| int32, non-null | `reference_year`, `occurrences` |
| bool, non-null | `source_is_comparative`, `has_value_change` |

Preserve the canonical key `(metric_id, unit, period_start, period_end, definition_version)`, reported scale and normalized value. `period_end` dates the observation; `release_reference_period` dates the release's reporting period; filing dates date disclosure. Comparative facts must not be relabeled as current-period facts. Bronze references identify lineage, not files that must be distributed or fetched.

### Manifest contrac

Require `contract_version` (string), `bundle_id` (`v1`), `source_code_revision` (Git SHA), `snapshot_cutoff` (ISO date), `generated_at` (UTC timestamp), and `datasets` (object keyed by exactly the two approved dataset IDs). Each dataset entry requires its exact relative `path`, `sha256`, positive `row_count`, `schema_name`, `schema_version`, minimum/maximum `period_end`, included `metric_ids` and `period_types`, source families/identifiers, and a documented source-review/attribution reference. Operational metadata also lists `definition_versions`. Record the deterministic row-selection rule and input version identifiers, plus the two excluded and ten intentionally omitted IDs.

This manifest is new release metadata, not a parallel data schema. It must contain no credentials, personal contact, private machine paths or signed/credential-bearing URLs. Checksums identify the distributed files; reviewers verify provenance references separately. An unreviewed manifest cannot grant itself clearance. No production writer metadata needs to be copied wholesale.

## Provenance requirements

Financial rows retain source, CIK/entity, metric/taxonomy/concept, form/accession, units, reporting periods, filing/revision dates and derivation flags. Operational rows additionally retain source URL, content hash, source-document identifier, definition version and comparative/revision information. Preserve source IDs and attribution required by the completed review.

Do not bundle raw SEC Company Facts JSON, Company release HTML, BCB/SIDRA responses or Twelve Data payloads. Public facts and copied document text are different review surfaces. Prefer numerical rows and enough lineage to identify their authoritative origin.

Before exporting, inspect provenance fields for private absolute paths or credentials. If a source-document identifier contains a personal filesystem prefix, withhold the artifact until a reviewed portable identifier mapping is defined and recorded without exposing that prefix; preserve accession and content hash. Do not silently delete lineage or falsify identifiers. Reader compatibility alone is insufficient approval.

## Snapshot and update policy

- Choose and record one cutoff before assembling the release. Include only selected observations and disclosures available by that cutoff; record each dataset's actual coverage. The cutoff is not the server's current date.
- Each bundle version is immutable: reviewed inputs, explicit row selection, schema versions, deterministic ordering and recorded artifact hashes make it reproducible. Record the exporter/library versions if byte-identical Parquet rebuilding is required.
- Refresh manually, normally after a quarterly filing/release and renewed review. No scheduled or request-time ingestion is required. Publish changes as a new bundle version; never overwrite an existing release silently.
- Display a portfolio-demo banner, bundle version, static cutoff, source families and per-dataset latest observation dates. Distinguish observation, filing and generation dates. A new build timestamp does not make old evidence fresh.
- Display coverage gaps as gaps; do not forward-fill missing observations or claim automatic freshness. Omitted optional domains are intentional scope, not application failures.

## Repository policy

Use tracked `demo_data/v1/` with exactly the three files above after review. Existing ignored `data/bronze`, `data/silver` and `data/gold` remain unchanged; do not force-add production outputs or relax their ignore rules. `demo_data/` is separate from those ignore patterns. No directory or bundle is created by this audit.

Release review must inspect the exact tracked artifact list and reject raw archives, Market artifacts, databases, credentials, extra sidecars and unlisted files. No recursive copy of production data and no directory discovery/glob to choose datasets. Optional dataset additions require a reviewed contract/version change. Main's 39-file inventory is not a distribution manifest.

Resolve paths from the verified source-tree project root using `pathlib` components and exact casing. The source-tree/editable installation assumption identified in Sprint 8B still needs target-Linux verification; arbitrary wheel layouts must not silently select another root.

## Future MELI_PUBLIC_DEMO contrac

Recommend this explicit mode, but **do not implement it in Sprint 8C**. Absent or `0` means OFF, preserving current local catalog, readers and behavior. `1` means ON. Reject other supplied values with an explicit configuration error instead of falling back to local mode.

When ON:

1. Keep the 14 dataset identities visible for coverage reporting, but authorize reads only for the two reviewed paths in the selected static bundle. No environment-selected arbitrary data root.
2. Show the public portfolio/static-snapshot banner and intentional omissions. Source previews obey the same policy as charts and valuation loaders.
3. Require no `TWELVE_DATA_API_KEY` or `SEC_USER_AGENT`; no source client construction, runtime ingestion or HTTP fetch. Existing UI has no ingestion controls; any future controls must be inaccessible in this mode.
4. For excluded Market datasets, display unavailable with the policy reason and no numeric price-dependent output. For ten unselected optional datasets, display explicit missing/unavailable scope, with no empty synthetic files or invented content.
5. Missing approved artifacts remain `MISSING`; empty or invalid ones retain those states and fail useful-demo acceptance. Keep diagnostic limitations visible. Policy explanations supplement existing health semantics, rather than changing analytical statuses or formulas.
6. Preserve financial selection, valuation eligibility and evidence semantics. No source replacement, Market-to-Product inference, synthesized hypotheses, zero filling or synthetic-to-real relabeling.

## Fail-closed behavior

Authorize the dataset ID and resolved path **before any file inspection or reader call**. Enforce this across catalog selection, health checks, shared loading, explicit `path=` overrides, Data Quality previews and Market valuation loading. Changing defaults alone is insufficient because current APIs accept caller-provided paths.

No fallback from `demo_data/` to `data/`, from a missing approved file to another filename, or from an excluded dataset to cached local data. Excluded Market files stay inaccessible even when present under production paths or accidentally placed inside the demo directory. Optional omitted files likewise are not auto-discovered.

Validate exact allowlisted relative paths, root containment after resolution, schema, hash and manifest identity. Reject traversal, absolute-path injection, symlink/reparse-point escapes and unlisted manifest datasets. A manifest cannot extend the hardcoded reviewed allowlist. Reject an invalid bundle with an explicit diagnostic, not unverified partial data or a local-mode fallback. Keep mode/bundle identity isolated in any caches so switching modes cannot expose private frames. These are future implementation requirements, not properties claimed of today's loader.

## Sprint 8D acceptance criteria

Tests must use temporary fixtures, never production `data/`. Publication tests for the approved real bundle are separate from synthetic unit-test fixtures.

1. Configuration: absent/`0` selects unchanged local mode; `1` selects public mode; invalid values fail explicitly. Local catalog paths and existing page contracts remain unchanged when OFF.
2. Inventory: exactly 14 IDs; exactly two approved read paths, two denied Market IDs and ten intentional omissions. Unknown IDs cannot be read.
3. Isolation: plant distinguishable local Market, Market Cap and optional fixtures, then exercise every page, health table, source preview and direct shared-loader/path override. Assert no excluded file is opened and no value reaches the UI. Remove an approved demo file while a valid production equivalent exists; assert MISSING and zero fallback reads.
4. Integrity: reject altered hashes, schemas, empty core files, unlisted paths, traversal, absolute paths and link escapes. Reject a manifest trying to approve Market. Verify any mode/cache transition cannot return local frames in public mode.
5. Offline: remove source keys from the process environment and block outbound network calls during startup and navigation; all ten pages initialize without ingestion. Assert no source clients/fetch functions are invoked. Do not rely only on HTTP health to prove page execution.
6. Useful coverage: with reviewed bundle inputs, execute existing Executive/Financial/Commerce/Fintech selectors and page tests. Verify nonempty factual snapshots and at least two eligible revenue/GMV/TPV trend points, MAU availability, correct units/periods and provenance/date inspection in Data Quality. Optional credit/risk measures may be missing.
7. Partial states: Macro, Product Evidence, PESTEL, SWOT and interpretation sections remain explicitly unavailable where omitted; no hypotheses/classifications, fabricated zeroes or unsupported takeaways appear. Market remains policy-unavailable even alongside usable Company facts.
8. Valuation/evidence parity: compare existing analytical results on identical allowed input frames in both modes; no formula, financial-selection or evidence-methodology changes. Assert no numeric multiple depending on excluded prices, no Market-to-Product inference, and unchanged TTM/P/E limitations.
9. Distribution: inspect tracked `demo_data/` against the three-file allowlist, validate source-review records, hashes, schema/provenance and absence of restricted/raw/secret artifacts. Confirm ignored production paths remain ignored. Review is required before adding real files.
10. Deployment: from a fresh Linux checkout with recorded dependency versions and source-tree installation, run the actual entrypoint, all-page navigation and read-only missing/partial/core-bundle cases. Verify exact path casing, root resolution and no writes to production data. Document provider assumptions separately.
11. Regression: full pytest remains green (Sprint 8C baseline 544 passed, 1 deselected); new tests may increase the count. Compile source/entrypoint and run `git diff --check`. Preserve `v1.0.0` and analytical code boundaries.

## Deferred questions

Publication blockers: complete dataset-level source/attribution review for the two proposed Company artifacts; select and verify actual eligible rows, cutoff and public-safe lineage. No permission is inferred from SEC/IR authority or numerical transformation. Obtain a documented review decision before tracking real artifacts.

Deployment prerequisites carried from Sprint 8B: validate a fresh Linux dependency resolution, source-tree artifact roots and the target hosting configuration. Optional later work: reviewed extended Fintech evidence, Macro and linked strategy/Product artifacts; separately cleared Market sources; external artifact hosting or a clearly separated synthetic demonstration. None is required to make the two-file factual core useful.

## Final recommendation

**REQUIRES_MORE_SOURCE_REVIEW**

The runtime and existing schemas support a small, deterministic Company-only demo using `financial_facts` and `operational_kpis`. The repository does not yet establish clearance to publish those snapshots. Resolve that review, then implement the isolated public catalog and assemble the reviewed bundle under Sprint 8D acceptance gates. Offline implementation scaffolding can be developed separately, but this contract is not approval to redistribute data or deploy uncleared artifacts. Market prices and price-derived Market Cap remain excluded; ten optional datasets may remain intentionally missing.
