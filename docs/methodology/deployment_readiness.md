# Deployment Readiness

## Executive verdict

**READY_WITH_FIXES** — the read-only application starts and all ten pages initialize in a clean checkout without credentials or production data. It is **not yet a useful, cleared public portfolio deployment**: all 14 dashboard datasets are absent, redistribution permissions are not established, and a reproducible target-Linux installation has not been validated.

Audit date: 2026-10-07. Baseline: `99085523f39bd3070bc1f6580d070a1392da2e3a`. This is an audit only; no implementation, data publication, dependency installation or external HTTP request was performed. The `v1.0.0` tag remains unchanged.

| Readiness dimension | Finding |
| --- | --- |
| Application/runtime | PASS in the existing Python environment: server health and complete clean-checkout navigation succeed. |
| Data availability | BLOCKER for a useful real-evidence demo: 0 of 14 cataloged datasets available. Missing-data handling itself works. |
| Public-data/licensing | BLOCKER for publishing an uncleared snapshot. Twelve Data prices and price-derived artifacts must remain excluded unless permission is confirmed. |
| Secrets/configuration | PASS for credential-free read-only startup. No live secrets detected in the tracked-file review. |
| Linux portability | Static review finds no Windows-only execution blocker. Source-location assumptions and a fresh Linux install require deployment validation. |
| Portfolio/demo | A functioning empty application demonstrates graceful degradation, but cannot demonstrate the intended evidence-led analysis. |

Technical startup readiness is distinct from useful public-demo readiness. Blocking publication of uncleared data does not mean authoritative public-source facts are prohibited; this audit has not established redistribution rights.

## Runtime readiness

The Streamlit entrypoint imports local presentation, catalog, filter and health modules. Health checks test file existence before querying missing files. The UI reads through `ui/data.py` and existing query functions, or through the validating Market Cap Gold reader. It does not ingest data. The catalog marks its datasets optional.

All 13 explicit catalog query/reader targets imported successfully from this worktree; Market prices use the generic DuckDB Parquet reader. Reviewed query modules: `duckdb`, `operational`, `extended_operational`, `macro`, `macro_analytics`, `evidence`, `pestel`, `swot`, `product_evidence`. Reviewed storage modules supplying paths, schemas or readers: `silver`, `operational_silver`, `extended_operational`, `macro`, `macro_analytics`, `evidence`, `pestel`, `swot`, `product_evidence`, `market_prices`, `market_cap`.

DuckDB connections use in-memory databases and parameterized file/filter values. Storage writers exist in the package but are not invoked by the read-only UI. Market Cap Gold is consumed as persisted data; the UI does not reconstruct it from price/share inputs. Missing paths remain missing rather than being populated or repaired.

This audit proves startup and empty-state execution, not public-host capacity, concurrent-user behavior, network security configuration or fresh dependency installation.

## Clean-checkout behavior

The entire worktree `data/` inventory is:

```text
data/
  bronze/
    .gitkeep  (0 bytes)
  gold/
    .gitkeep  (0 bytes)
  silver/
    .gitkeep  (0 bytes)
```

These three files are tracked. No other files or directories exist below `data/`. No Parquet files, sidecars, databases or source payloads were copied or generated. The main checkout contained 39 files under `data/`, including skeleton files; it was inspected only for an unchanged-state hash manifest, not used as the demo dataset.

The main repository's existing interpreter was used with `PYTHONPATH` explicitly pointing to this worktree's `src`. Runtime settings and catalog-reader module paths were verified to resolve here. `SEC_USER_AGENT`, `TWELVE_DATA_API_KEY` and `LOG_LEVEL` were removed from the smoke-test process environment; this checkout has no `.env`.

| Smoke check | Observed result |
| --- | --- |
| `python -m streamlit run streamlit_app.py` from repository root | Process started; headless mode, telemetry disabled, loopback binding, a temporary free port and file watching disabled for the smoke. |
| Local `/_stcore/health` | HTTP 200, body `ok`. Only loopback HTTP was used. |
| Server logs and shutdown | No Python traceback in server logs; process terminated and shutdown confirmed. |
| Catalog health | 14 `MISSING`, 0 `AVAILABLE`. |
| Script execution, not just server health | Streamlit `AppTest` executed the entrypoint and selected every navigation option with real missing-file health checks. |
| Navigation | Executive Overview, Financial, Commerce, Fintech, Macro, PESTEL, SWOT, Product Evidence, Market and Data Quality & Sources: no application exceptions; explicit missing/unavailable messages. |
| Ingestion/network | No ingestion; no external connection attempts during navigation. External socket connections were blocked in the AppTest harness; loopback was permitted for Windows asyncio. |

A health response alone does not execute every page, which is why the separate AppTest run matters. No synthetic or production dataset was created for this smoke. Initial harness retries addressed sandbox temporary-directory cleanup and an overly broad socket guard that blocked Windows asyncio's loopback socketpair. The final navigation run exited successfully without a traceback; the expected bare-mode ScriptRunContext warning is a testing-harness warning, not an application exception.

## Linux portability

Classification: PASS = supported by inspected evidence; MINOR = optional portability polish; SHOULD_FIX = deployment preparation/verification needed; BLOCKER = demonstrated inability to deploy the proposed application. No Linux runtime was available for execution in this audit; static PASS findings are not Linux certification.

| Concern | Classification | Evidence / consequence |
| --- | --- | --- |
| Hardcoded drive paths or backslash-only file opens | PASS | No drive-path literals in production source/entrypoint and no backslash-only literal arguments to `Path`/`open` found. Paths use `pathlib`, file-relative roots and path components. |
| Assumption about a particular Windows checkout | PASS | No production reference to the owner's Windows checkout. Machine-path text exists in a historical methodology note and negative portability test, not runtime resolution. |
| Case-sensitive filenames/imports | PASS | No case-colliding tracked paths or mismatched local module import casing found; all catalog reader targets resolve. Actual future artifact names must match the catalog exactly. |
| Working directory and installation layout | SHOULD_FIX | `config/settings.py:11` derives `PROJECT_ROOT` from `Path(__file__).resolve().parents[3]`. This works for source-tree imports; a normal non-editable installation moves that base outside the checkout. Select and verify an editable/source-tree deployment recipe. |
| Shell-specific application behavior | PASS | No production subprocess, `os.system`, Windows registry or Windows-specific runtime branch found. Streamlit is a Python module entrypoint. |
| Setup documentation | MINOR | README activation instructions are PowerShell-specific. A future Linux runbook needs its own activation/build instructions; this is not an application runtime defect. |
| Temporary files / filesystem | PASS for read-only startup | Missing-data startup does not require writes to `data/`. Existing storage writers use `tempfile.mkstemp`, descriptor handling and `os.replace`; no fixed Windows temp directory is embedded. Deployment-time ingestion would separately require writable artifact storage. |
| Timezone database | MINOR, ingestion only | `pipelines/market_prices.py:29` constructs `ZoneInfo("America/New_York")`. That pipeline is not imported by the dashboard. If deploy-time ingestion were chosen, verify system timezone data in the target image; do not assume it in a minimal image. |
| Target OS validation | SHOULD_FIX | Current runtime evidence is Windows/Python 3.14.7. A clean Linux build and page smoke with the selected artifact bundle remain acceptance tasks, not demonstrated source defects. |

## Dependencies

Every direct non-standard-library production import is represented in `pyproject.toml`:

| Import / package | Declared runtime constraint | Version used in this audit |
| --- | --- | --- |
| `dotenv` / python-dotenv | `>=1.0` | 1.2.4 |
| `httpx` | `>=0.27` | 0.28.1 |
| `pandas` | `>=2.2` | 3.0.6 |
| `pyarrow` | `>=18` | 25.0.1 |
| `duckdb` | `>=1.1` | 1.5.6 |
| `bs4` / beautifulsoup4 | `>=4.12` | 4.15.0 |
| `streamlit` | `>=1.36` | 1.65.0 |

DuckDB, PyArrow, Pandas and Streamlit are explicit dependencies. `setuptools>=68` is a build requirement. `pytest`, `pytest-cov` and Ruff are confined to the optional `dev` extra; the dashboard does not import them. README's `.[dev]` installation is a development convenience, not a public-runtime requirement. HTTPX and Beautiful Soup support ingestion in the single package; they need not execute for read-only startup. A runtime/ingestion dependency split is optional future packaging work.

Python `>=3.11` is a reasonable modern baseline, but no cloud provider's supported interpreter list was checked. Select a provider-supported Python version and verify wheels for the complete dependency set. This audit used Python 3.14.7; it does not prove the minimum versions work. Lower bounds are open-ended, no lock/constraints file is tracked, and native Streamlit calls such as `width="stretch"` and chart axis-label parameters were only executed with 1.65.0. Minimum-version compatibility must not be inferred from the successful local environment.

**SHOULD_FIX:** establish a tested Linux dependency resolution and record/pin it for deployment. No missing direct dependency or accidental undeclared local-only import was found, but the main virtual environment is not a substitute for a clean install test. No packages were installed or updated during this audit.

## Entrypoint

The command is suitable **after explicit installation/source-path setup**, from the repository root:

```text
python -m streamlit run streamlit_app.py
```

Setuptools discovers packages under `src`. Pytest's `pythonpath = ["src"]` applies to tests, not automatically to a hosted Streamlit process. A proposed deployment build can use `python -m pip install -e .` to install runtime dependencies and preserve source-tree resolution. Alternatively, the launcher must explicitly expose this checkout's `src` through `PYTHONPATH` while installing its declared dependencies. These are future deployment instructions, not commands executed in this audit.

Do not assume a host automatically installs the project or selects editable mode. The app does not require the process working directory for data resolution once imported, but the relative entrypoint command requires repository-root execution. A wheel-only deployment would need an explicit artifact-location design because settings currently derive data paths from the module location. No environment variable currently overrides `DATA_DIR`.

Provider selection, dependency detection, port binding, proxy/TLS handling, build persistence and resource limits are deployment assumptions to validate later. No Streamlit Community Cloud-specific behavior is asserted here.

## Secrets and configuration

| Variable | Classification | Required for read-only dashboard startup? | Evidence |
| --- | --- | --- | --- |
| `SEC_USER_AGENT` | Required only for SEC ingestion, unless passed explicitly | No | Settings read it optionally; the SEC client enforces it when constructed for source requests. Example is a descriptive contact placeholder. |
| `TWELVE_DATA_API_KEY` | Required only for Twelve Data ingestion, unless passed explicitly | No | `sources/market/twelve_data.py:90` reads it on fetch. Example is empty. |
| `LOG_LEVEL` | Currently unused environment variable | No | Example contains `INFO`; logging setup takes a function argument and does not read this variable. |

The public read-only application can run without a Twelve Data API key, as verified. Credentials neither create missing datasets nor authorize their redistribution. No secrets need to be copied into a demo checkout. `MELI_PUBLIC_DEMO` does not exist in the current configuration.

Tracked-file security review:

- `.env` is ignored and untracked; only `.env.example` is tracked. No `.env` exists in this worktree.
- No recognizable live API-key/private-key patterns or generated credential files were detected. Literal credential scan hits are offline test fixtures, not production settings. This is a bounded repository scan, not a credential-history or security certification.
- Email-like hits occur only in test fixtures using reserved example domains: `tests/unit/test_sec_client.py:49,61,77` and `tests/unit/test_sec_operational_releases.py:118,157`. No personal contact found in tracked production configuration/code, README or examples. Values are deliberately not reproduced here.
- Absolute machine-path hits occur in `docs/methodology/market_source_validation.md:11` and `tests/unit/test_streamlit_foundation.py:40`; the latter contains a personal-path negative-test fixture. Neither is a runtime dependency. Consider neutralizing these public-facing references later; no source was edited.
- No tracked source payloads, Parquet/DB files or credential archives were found. Test data is synthetic fixture material, not a redistribution source for a real-data demo.
- Data Quality & Sources displays resolved filesystem paths in technical details. That is not a secret by itself, but public-demo path/provenance review should prevent publishing unnecessary personal prefixes from future artifacts.
- The app has no ingestion/upload controls; the entrypoint's button resets filters. Query inputs use local catalog paths rather than arbitrary user-supplied filesystem locations. This does not replace host-level security review.

## Data availability matrix

Every row is `MISSING` in this checkout. Paths are relative to the repository root. No dataset is mandatory for startup. “Required” below means useful coverage for the proposed portfolio narrative, not a runtime dependency.

Classification:

- **A — SAFE_CANDIDATE_FOR_PUBLIC_STATIC_DEMO:** suitable for a curated, source-reviewed candidate bundle; not a legal clearance. Upstream rights, attribution and copied text still need review.
- **B — REQUIRES_SOURCE_TERMS_REVIEW:** source-derived facts/text whose applicable terms and attribution have not been established by project evidence.
- **C — DO_NOT_REDISTRIBUTE_WITHOUT_LICENSE_CONFIRMATION:** exclude from the initial public bundle, including restricted-source derived artifacts.
- **D — NOT_NEEDED_FOR_PUBLIC_DEMO:** omit from the initial bundle; this says nothing about permission if included later.

| dataset_id | Expected local path | Required for useful demo? | Behavior if missing | Public redistribution concern / class | Candidate public-demo strategy |
| --- | --- | --- | --- | --- | --- |
| `financial_facts` | `data/silver/sec/financial_facts.parquet` | Core Company coverage | Financial facts/chart unavailable; no zero substitution | B: SEC/Company reported facts; review selected fields and provenance | Small, dated, terms-reviewed numerical Company snapshot |
| `operational_kpis` | `data/silver/sec/operational_kpis.parquet` | Core Commerce/Fintech coverage | Priority KPIs/charts unavailable | B: Company release facts and definitions | Curated KPI periods retaining units, definitions and source IDs |
| `extended_operational_kpis` | `data/silver/sec/extended_operational_kpis.parquet` | Optional additional Fintech context | Extended measures unavailable; base KPIs remain independent | B: Company disclosures and qualifiers | Include only reviewed measures needed for the story |
| `extended_operational_evidence` | `data/silver/sec/evidence_facts.parquet` | Optional; catalog/lineage detail | Missing in Data Quality & Sources; no replacement facts | D: not needed for first demo; Company text needs review if later included | Omit initially; preserve necessary lineage in chosen evidence artifacts |
| `macro_indicators` | `data/silver/macro/macro_indicators.parquet` | Core Macro coverage | Macro measures/series unavailable | B: BCB and IBGE/SIDRA facts; public authority does not establish terms here | Small official-source snapshot after attribution/terms review |
| `macro_analytics` | `data/gold/macro/macro_analytics.parquet` | Optional derived context | Derived context unavailable | A: project-derived numerical output, conditional on reviewed upstream data | Include existing derived outputs from the approved snapshot only |
| `macro_evidence` | `data/gold/macro/macro_evidence.parquet` | Useful for evidence narrative | Existing observations unavailable | A: project observation text with official-source lineage | Review text and include compatible dated observations |
| `evidence_registry` | `data/gold/evidence/evidence_registry.parquet` | Core if demonstrating linked Product evidence | Linked records unavailable; persisted IDs remain visible | B: mixed source facts/text and derived observations | Curate a complete, source-reviewed lineage subset; no restricted Market inputs |
| `interpretations` | `data/gold/evidence/interpretations.parquet` | Useful for strategic narrative | Explicit absence of existing interpretations | A: project rule-based text; upstream evidence must be cleared | Include existing interpretations linked to the approved registry |
| `pestel` | `data/gold/strategy/pestel.parquet` | Required only to showcase PESTEL | Missing classification state; no fabricated dimensions | A: project classification plus inherited claims/lineage | Include only reviewed classifications with complete evidence lineage |
| `swot` | `data/gold/strategy/swot.parquet` | Required only to showcase SWOT | Missing state; quadrants not artificially filled | A: project synthesis plus inherited claims/lineage | Retain categories and links; include only reviewed rows |
| `product_evidence` | `data/gold/product/product_evidence.parquet` | Required to showcase Product Discovery | Missing hypotheses/questions; aggregate-data limitations remain visible | A: project hypotheses/questions with upstream evidence and text obligations | Curate persisted records and their complete approved lineage; never invent opportunities |
| `market_prices` | `data/silver/market/market_prices.parquet` | No for initial public demo | Explicit missing price/history state | C: Twelve Data redistribution not confirmed | Exclude until licensed; do not commit provider payloads |
| `market_capitalization` | `data/gold/market/market_capitalization.parquet` | No for initial public demo | Market cap and dependent valuation unavailable | C: derived from Twelve Data close; derivation does not establish redistribution rights | Exclude alongside prices pending license review; preserve valuation unavailable states |

Additional artifacts: `data/silver/company/shares_outstanding.parquet` is an upstream Market Cap input, not a direct Streamlit catalog dataset; the read-only app consumes Gold rather than rebuilding it. It is D for the initial non-Market demo, with SEC/Company source review needed if later distributed. Raw Bronze SEC/IR, BCB, IBGE and Twelve Data payloads and write-side metadata files are not needed for read-only startup. Do not publish whole raw releases or provider responses simply because they were locally ingested. Retain public-safe source URLs, IDs, periods, methodology versions and lineage in curated artifacts.

## Public-data / licensing considerations

The repository establishes source authority, not blanket redistribution permission. README and `market_data.md:39` explicitly limit the existing Twelve Data approval to local/internal use and require redistribution review. Those statements support conservative exclusion; this audit did not contact providers, inspect current online terms or obtain legal clearance.

Distinguish:

1. **Authoritative facts:** SEC, Company IR, BCB and IBGE provenance supports factual authority. It does not by itself establish permissions for copied tables, wording, document payloads or public hosting.
2. **Transformed snapshots:** a small numerical Parquet subset reduces scope and payload exposure, but still needs applicable source/attribution review. Preserve definitions and dates; do not modify facts to make a demonstration more persuasive.
3. **Derived evidence:** project-generated analytics, interpretations and classifications may be good candidates, provided their source material and any embedded claims are approved. Preserve lineage; do not assume derived data escapes source restrictions.
4. **Third-party Market data:** Twelve Data history and Market Cap Gold incorporating its prices are excluded by default. Hosting externally, removing an API key or calculating a multiple does not resolve licensing.

No software license has been selected in the repository. This audit adds none and makes no open-source license claim. The owner should decide distribution terms separately; software licensing does not grant rights in third-party data.

## Recommended public-demo architecture

Use a **curated static Company/Macro/evidence bundle plus an explicitly partial public application**. This combines options 1 and 4 below, with option 5's exclusion of Market price history and its price-derived valuation inputs. If source review is unfinished, deploy only the clearly described empty/partial shell, not an uncleared dataset; that shell remains a limited portfolio demonstration.

| Option | Benefits | Costs / constraints | Recommendation |
| --- | --- | --- | --- |
| 1. Commit curated public-demo data | Small, versioned, reproducible; no request-time credentials | Needs explicit source review, artifact provenance and an intentional tracked location/build mapping; current `data/` outputs are ignored | Preferred after review, using a separate curated bundle rather than copying production `data/` |
| 2. Build data at deploy time | Avoids committing source artifacts | External requests, source availability/rate limits, SEC identification, writable build storage, deterministic pipeline sequencing and rights review remain necessary | Avoid for the first portfolio deployment; no such build was attempted |
| 3. Host static artifacts externally | Separates app code and artifact releases | Adds hosting/access/checksum/download coordination; public redistribution concerns remain identical | Defer unless approved bundle size or update frequency warrants it |
| 4. Partial datasets with explicit unavailable states | Already supported; no fabricated completeness | An entirely empty instance does not demonstrate analysis | Preferred fallback; populate a reviewed core before presenting it as the portfolio demo |
| 5. Disable public Market history, retain Company evidence | Avoids distributing unlicensed provider history | Must also exclude Market Cap Gold and dependent price-based outputs; explain omitted scope | Recommended initial scope; existing missing states suffice, explicit public catalog is a future improvement |
| 6. Clearly labeled synthetic/sample Market data | Could demonstrate chart mechanics without provider payloads | Requires separate provenance, catalog and persistent demo labeling; risks contamination of real valuation/evidence | Optional later sandbox only; not a substitute for real evidence and not needed initially |

Proposed preparation, not implemented here: review terms and attribution; select a small coherent period range; package compatible Silver/Gold rows and all referenced evidence IDs; record hashes, schema/methodology versions, coverage and sources; explicitly exclude Market prices/Market Cap Gold/raw payloads; install the package with source-tree imports; map only approved artifacts into expected paths in the deployment image; run read-only smoke and regression checks. Never copy all 39 main-checkout files wholesale or force-add ignored production outputs.

### Future public-demo mode

A future `MELI_PUBLIC_DEMO=1` is recommended as a clear scope control, but is not implemented or required to run today's empty shell.

It should:

- Choose an explicit public artifact root/catalog with an allowlist and **no fallback to private local `data/`**.
- Exclude unapproved Market prices, price-derived Gold and any other uncleared records from loading and previews, even if files happen to exist on the host.
- Show a portfolio-demo banner with static coverage dates and disclose intentional exclusions separately from missing approved files.
- Keep approved source/period/lineage detail available without personal filesystem prefixes or credential-bearing URLs.
- Remain read-only. There are currently no ingestion controls to disable; any future ones must be unavailable in public mode.

It must never alter formulas, financial selection, valuation eligibility, source facts or evidence semantics; fill missing values; synthesize Product hypotheses; infer behavior from Market data; expose secrets; or relabel synthetic data as real. Suppression is a presentation/access decision, not a new backend analytical status or a way to bypass methodology. P/S and P/Operating Cash Flow still require valid TTM contracts; P/E remains outside scope. No Buy/Sell/Hold, target price, fair value or trading recommendation is introduced.

## Required fixes before deployment

Publication blockers and required actions are separate from optional polish:

| ID | Severity / blocker | Required resolution |
| --- | --- | --- |
| B1 | BLOCKER for useful evidence-led demo: all catalog datasets absent | Provide a reviewed, coherent core static snapshot and explicit coverage description, or deliberately accept/document an empty-shell demonstration with limited portfolio value. Credentials alone do not solve this. |
| B2 | BLOCKER for publishing uncleared data: source permissions unresolved | Record source/attribution review for every distributed dataset. Exclude Twelve Data prices and dependent price-derived artifacts unless license confirmation explicitly covers intended public use. A non-Market demo does not need a Twelve Data license if none of its restricted artifacts are distributed. |
| R1 | SHOULD_FIX: install/artifact-root contract unspecified | Choose editable/source-tree import configuration and an explicit approved-artifact mapping. Verify `PROJECT_ROOT` and catalog paths in the deployed image; do not rely on the main virtual environment or pytest's path setting. |
| R2 | SHOULD_FIX: Linux dependency resolution untested/unlocked | Select provider-supported Python, record a tested dependency resolution, then run a fresh Linux install, regression and populated/partial/missing-data smoke. Do not assume declared minimum Streamlit versions support every used API. |

No production-code fix was demonstrated as necessary for the clean-checkout startup path. Future public-catalog implementation would be a separate authorized sprint.

## Deferred improvements

- Add public-mode catalog isolation and banner as designed above; a carefully isolated partial artifact image can precede it.
- Add a Linux deployment runbook and optional automated release smoke; select provider specifics only after testing that provider.
- Review path-display minimization, historical machine-path text and the negative personal-path test fixture. No secret remediation was required by this scan.
- Consider explicit closing/context management for short-lived DuckDB connections in `query/operational.py` and `query/extended_operational.py`; these currently return from chained connection calls. No failure or resource exhaustion was demonstrated.
- Separate ingestion-only dependencies if runtime size becomes an issue; benchmark actual memory/concurrency before optimization.
- Defer deploy-time ingestion, external artifact hosting and synthetic Market demonstrations until they have explicit provenance, licensing and operational contracts.

### Repository and deployment size

At the audited baseline, Git tracks **199 files totaling 1,129,490 uncompressed blob bytes (about 1.08 MiB)**. This is the current tracked tree, not Git history, a virtual environment, an image or deployed dependency size. The working-tree byte total differs because of checkout line endings.

| Largest tracked file | Git blob bytes |
| --- | ---: |
| `src/meli_intelligence/product/evidence.py` | 26,037 |
| `src/meli_intelligence/metadata/kpi_dictionary.py` | 24,200 |
| `src/meli_intelligence/analytics/valuation.py` | 23,063 |
| `src/meli_intelligence/strategy/swot.py` | 21,808 |
| `tests/unit/test_macro_analytics_and_evidence.py` | 19,982 |

No unnecessarily large tracked artifact was identified. Generated data and the virtual environment are excluded. Pandas/PyArrow/DuckDB/Streamlit and their transitive dependencies will dominate runtime installation size; that footprint was not measured here.

## Deployment acceptance checklist

Completed in this audit:

- [x] Baseline verified; existing `v1.0.0` tag left untouched.
- [x] Clean worktree inventory: only three tracked zero-byte data placeholders.
- [x] Credential-free server start; loopback health HTTP 200 `ok`; server stopped.
- [x] All ten navigation pages executed with missing production data and no application exceptions.
- [x] No external HTTP requests, ingestion, copied production data or writes under repository `data/`.
- [x] `python -m pytest -p no:cacheprovider`: **544 passed, 1 deselected**; external-service integration test excluded by project configuration.
- [x] `python -m compileall src` and `python -m py_compile streamlit_app.py`: passed. Bytecode redirected to temporary storage.
- [x] Only this audit document added; production code, configuration and tests unchanged.

Before publishing a useful public demo:

- [ ] Resolve B1 with a reviewed core bundle, or explicitly accept empty-shell scope.
- [ ] Resolve B2 with a dataset-level terms/attribution record and restricted-data exclusions.
- [ ] Verify artifact schema, periods, evidence lineage and public-safe metadata; no synthetic-to-real relabeling.
- [ ] Resolve R1: tested source-tree imports, entrypoint and artifact paths on the target host.
- [ ] Resolve R2: fresh Linux install with recorded dependency versions; no hidden main-environment dependency.
- [ ] Test populated, deliberately partial and missing bundle cases without source credentials or ingestion.
- [ ] Verify the public process cannot load excluded/private datasets and that omissions are clearly disclosed.
- [ ] Confirm provider-specific TLS/proxy, port, filesystem, resource and logging settings without exposing secrets.

Final delivery checks also compare data manifests, main tracked-file hashes/status/HEAD and the release tag, and run `git diff --check`. No fixes, deployment or commits are performed by this audit.
