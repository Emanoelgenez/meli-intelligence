# Public Source Review

## Scope and non-legal disclaimer

Review date: **2026-10-07**. Repository baseline: `e6ac2a87a67b0e6e022d1780b28c3779ae913919`. This is an operational source-policy decision for a small static portfolio snapshot of exactly `financial_facts` and `operational_kpis`, not legal advice or a blanket license for Company content.

This review resolves the source-review gate in [Public Demo Data Contract](public_demo_data_contract.md) for the source chains below. It does not edit that historical contract, implement public mode, create artifacts, approve Market, or satisfy the remaining deployment acceptance tests in [Deployment Readiness](deployment_readiness.md). Only official SEC and MercadoLibre pages are used as policy authority. Web research was read-only; no ingestion or repository payload download occurred.

| Question | Decision boundary |
| --- | --- |
| Public accessibility | A readable page alone does not establish redistribution permission. |
| Automated access | SEC permits policy-compliant scripted access; rate limits and identification remain separate requirements. |
| Internal analysis | Existing local use does not itself authorize publication. |
| Transformation | Numeric normalization preserves source dependencies; changing file format does not create permission. |
| Transformed redistribution | The SEC's express dissemination and EDGAR reuse statements support the restricted factual snapshot defined here. They do not approve IR-only material or third-party Market data. |

## Provenance reconstruction

Read-only inspection covered the main checkout's two Silver Parquets, their available metadata, Company Facts Bronze JSON and seven operational Bronze documents/sidecars. Source hashes and provenance fields were checked without copying files. All production data files were hashed before and after the review for integrity verification.

### Financial chain

`SEC data.sec.gov Company Facts/XBRL → storage/bronze.py → data/bronze/sec/companyfacts/CIK0001099590_companyfacts.json → transformations/sec_companyfacts.py:normalize_company_facts → pipelines/sec_financials.py → storage/silver.py → data/silver/sec/financial_facts.parquet → query/duckdb.py → ui/data.py → Executive / Financial (and existing valuation input access)`.

`sources/sec/client.py` constructs the Company Facts endpoint. The persisted Bronze sidecar identifies `SEC EDGAR Company Facts API`, endpoint `https://data.sec.gov/api/xbrl/companyfacts/CIK0001099590.json`, and retrieval time `2026-10-06T23:13:06.189247+00:00`. The reviewed Bronze SHA-256 is `7ef80552e82d6e39c5d3d32671e5bb3fab189fd1bc486a3b1ad0671547736045`.

The 812 persisted Silver rows all identify that source, CIK `0001099590`, taxonomy `us-gaap`, and forms `10-K` or `10-Q`. Their period ends span 2007-12-31 through 2026-06-30. For **812/812**, the accession, period end and numeric value match an observation under the same taxonomy/concept/unit in the local Company Facts payload. This corroborates the source label; it is not an independent accounting audit of every value. The normalizer retains filing selection and revision metadata, and distinguishes period types. `analytics/financial.py` consumes those facts without changing their source rights.

The 26-column Silver schema contains numbers, identifiers, dates, short metric/entity labels and normalization/revision flags. It has no report narrative, HTML, source images or copied charts. The mapped metrics present are `capex_ppe_legacy`, `capex_productive_assets`, `cash_and_equivalents`, `gross_profit`, `net_income`, `net_revenues_financial_income`, `operating_cash_flow`, `operating_income`, `stockholders_equity`, `total_assets`, and `total_liabilities`. Presence does not make legacy capex analytically interchangeable with productive-assets capex.

### Operational chain

`SEC submissions / EDGAR filing index → sources/sec/operational_releases.py → EX-99.1 earnings-release exhibit → storage/operational_bronze.py → data/bronze/sec/operational_releases/*.htm plus metadata → transformations/operational_kpis.py:parse_operational_release → pipelines/operational_kpis_silver.py → storage/operational_silver.py canonicalization → data/silver/sec/operational_kpis.parquet → query/operational.py → ui/data.py → Executive / Commerce / Fintech`.

The discovery code looks for Item 2.02 Form 8-K submissions and exhibit 99/99.1. Critically, the pipeline assigns the SEC source label itself: **that label alone is not sufficient evidence**. This review also checked row URLs, accessions, document names, Bronze sidecars and content hashes. All 144 rows point to the seven SEC-hosted exhibits below; all row `source_content_sha256` values match the referenced local Bronze bytes. Sidecars record retrieval on 2026-10-05 between 15:32:34 and 15:32:35 UTC. All seven official exhibit URLs were independently opened in this review. A [filing index for accession 0001099590-25-000025](https://www.sec.gov/Archives/edgar/data/1099590/000109959025000025/0001099590-25-000025-index.html) also confirms its filing/exhibit context.

| Source ID | SEC accession | Release date / SEC-hosted EX-99.1 document |
| --- | --- | --- |
| E1 | `0001099590-25-000004` | [2025-02-20, meli-20250220xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959025000004/meli-20250220xex991.htm) |
| E2 | `0001099590-25-000025` | [2025-05-07, meli-20250507xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959025000025/meli-20250507xex991.htm) |
| E3 | `0001099590-25-000041` | [2025-08-04, meli-20250804xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959025000041/meli-20250804xex991.htm) |
| E4 | `0001099590-25-000048` | [2025-10-29, meli-20251029xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959025000048/meli-20251029xex991.htm) |
| E5 | `0001099590-26-000003` | [2026-02-24, meli-20260224xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959026000003/meli-20260224xex991.htm) |
| E6 | `0001099590-26-000014` | [2026-05-07, meli-20260507xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959026000014/meli-20260507xex991.htm) |
| E7 | `0001099590-26-000021` | [2026-08-05, meli-20260805xex991.htm](https://www.sec.gov/Archives/edgar/data/1099590/000109959026000021/meli-20260805xex991.htm) |

These are Company-authored disclosures publicly hosted through EDGAR, not government-authored financial claims. Release dates differ from the periods reported, including comparative periods. Do not replace economic-period dates with filing dates. No claim of byte equivalence between IR-hosted and EDGAR-hosted copies is needed or made.

The 29-column operational schema preserves numeric values, short KPI labels, units/scales, period and definition metadata, accession/URL/hash, source-file identifier and revision/comparative flags. It does not persist the exhibit's shareholder-letter narrative. Existing operational analytics and tests protect definition families, exact periods, TPV recasts, Fintech MAU instant semantics and NIMAL percentage-point treatment. Reuse approval changes none of those rules.

## Official SEC / EDGAR policy evidence

All sources below were reviewed on **2026-10-07**. Conclusions are paraphrases; policy scope is limited to the reviewed factual SEC source chains.

| Official source | Relevant conclusion | Implication / caveat |
| --- | --- | --- |
| [Privacy Information — Website Dissemination](https://www.sec.gov/about/privacy-information), displayed update 2023-11-29 | SEC.gov information may be copied and further distributed without SEC permission; appropriate source citation is requested. | Supports this factual snapshot. Do not use the SEC seal, logos or artwork. Names/logos have trademark restrictions; textual references must not imply affiliation or approval. |
| [Webmaster Frequently Asked Questions](https://www.sec.gov/about/webmaster-frequently-asked-questions), displayed update 2024-08-23 | Government-created SEC.gov material **and EDGAR public filing content** are free to access and reuse; some content, such as illustrative stock photography, is excepted. | The permission evidence covers public Company filing content, not just government prose. It does not justify copying all site assets. |
| [EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), displayed update 2025-04-08 | Public APIs expose submissions and extracted XBRL data without API keys. Company Facts aggregates company concepts; automated use must follow SEC access policies. | Confirms the financial endpoint's source role and credential-free public access. API documentation is not, by itself, the redistribution grant. |
| [Accessing EDGAR Data — Fair access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) | Maximum stated rate is 10 requests/second; use efficient, limited downloads and declare the User-Agent. SEC can restrict abusive access. | Future refresh tooling must identify itself, throttle aggregate traffic, cache and back off on denial/rate limiting. Never rotate identities to evade limits. Static dashboard serving requires no SEC requests. |

The [SEC Internet Security Policy](https://www.sec.gov/about/privacy-information#security) remains applicable to future acquisition. Permission to reuse is not permission to overload the service. Keep any operational contact identifier out of the public snapshot and logs. Do not embed credentials, use SEC trademarks in a misleading product identity, or suggest SEC review of this application. These are separate from permission to cite SEC in plain text.

## financial_facts review

**Classification: CLEARED_FOR_PUBLIC_TRANSFORMED_SNAPSHOT**

The actual persisted chain is SEC Company Facts/XBRL derived from public EDGAR financial filings, with row-level filing identifiers and verified matching observations. It is not an IR download mislabeled by filename. The proposed numerical/metadata-only subset fits the express SEC dissemination and EDGAR reuse policies above. No permission-dependent report narrative is required.

Clearance is for selecting eligible rows into the small versioned snapshot using the existing schema and methodology. It is not instruction to copy all 812 rows, ship Company Facts JSON, silently change latest-filing selection, or publish unrelated datasets. Match exported rows to the pinned Company Facts input and preserve the corresponding filing/revision provenance. A new input version must pass the same checks.

## operational_kpis review

**Classification: CLEARED_FOR_PUBLIC_TRANSFORMED_SNAPSHOT**

Every inspected metric family is category **A: SEC/EDGAR filing exhibit**. None depends on obtaining material from IR. The local artifact already has an EDGAR-backed chain, so an IR-to-EDGAR rebuild is not a prerequisite for these inspected rows. Nevertheless, a validated subset export is mandatory: a future file with the same name is not automatically approved.

| metric_id / KPI family | Persisted rows | Source family / document | SEC accessions | IR dependency? | Disclosure available through EDGAR? | Public-snapshot disposition |
| --- | ---: | --- | --- | --- | --- | --- |
| `gmv` / Commerce volume | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 above | None found | Yes, existing source chain | Include eligible quarterly subset |
| `unique_active_buyers` / Commerce activity | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Optional factual rows within core file |
| `items_sold` / Commerce activity | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Optional factual rows within core file |
| `fintech_mau` / Fintech activity | 11 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Include eligible INSTANT snapshots |
| `tpv` / Fintech payment volume | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Include eligible quarterly subset, preserving definitions |
| `acquiring_tpv` / acquiring volume | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Optional factual rows, same validation |
| `payment_transactions` / payment activity | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Optional factual rows, same validation |
| `nimal` / Company-reported lending measure | 19 | A; SEC-hosted Company EX-99.1 | E1–E7 | None found | Yes | Optional reported fact; do not recalculate or reinterpret |

Total: 144 rows across eight metric IDs, seven distinct documents for each family. The counts include period/definition variants and do not mean 19 comparable quarters. E1–E7 denote the exact accession/URL allowlist, not a wildcard for any exhibit.

The whole existing artifact passes the inspected source-family test, but it is **not automatically the approved distribution artifact**. The first public snapshot must be restricted by metric, period, disclosure cutoff, exact provenance and existing eligibility rules. Unknown source URLs, unmatched hashes or IR-only additions fail validation. If a later candidate truly originates only from IR, exclude it or separately acquire and rebuild from a verified EDGAR disclosure; changing its URL/source label is not a rebuild.

## MercadoLibre IR-only material

Reviewed the official [IR home](https://investor.mercadolibre.com/), [contact page](https://investor.mercadolibre.com/contact), and its linked [Privacy Statement](https://investor.mercadolibre.com/privacy) (updated 2026-01-20). The contact form mentions terms and links the privacy policy. That statement addresses personal-data processing on the investor site, not permission to republish disclosures. Official-domain searches for terms of use, copyright, redistribution and reproduction did not establish an explicit IR-content reuse grant. Search coverage and page extraction are finite; this is not a claim that no other terms exist.

**IR-only redistribution remains unresolved.** Neither silence nor a marketplace user agreement is used as permission. No contact form was submitted. No candidate row in the inspected two datasets was found to require IR-only permission: the operational disclosures already exist at the seven EDGAR URLs, and financial rows use Company Facts. Thus there is no missing IR-dependent KPI requiring a substitute in this bundle. A future IR-only addition needs its own review or a genuinely verified EDGAR source chain.

## Factual data versus expressive content

Distribute only the existing typed factual schemas: metric/fact IDs, numbers, units/currency, reporting and filing dates, short identifying labels, accession/source identifiers, lineage hashes and necessary normalization/methodology metadata. Preserve the actual source, even when Company-authored facts are accessed through SEC.

Do not distribute full releases, decks, HTML/PDF/JSON source archives, source-site screenshots, logos, copied charts or long narrative passages. Do not import the shareholder letters' engagement/causation claims into Product Evidence. Source approval does not validate a new analytical interpretation. Market/Company/Product separation and all valuation limitations remain unchanged.

## Required attribution

Attribution is a project release requirement; do not portray every field below as a statutory condition imposed by the SEC.

- Identify **MercadoLibre, Inc.** as reporting organization and **SEC EDGAR** as the dissemination/API source, using text only.
- Financial: identify Company Facts/XBRL, CIK, taxonomy/concept/unit, form/accession, observation period and filing date. Link the official API and, where practical, the exact filing index.
- Operational: identify the earnings-release EX-99.1 document, exact SEC URL/accession, release and economic-period dates, definition version, comparative/revision status and content hash.
- Preserve retrieval timestamps from metadata separately from public-bundle build time and snapshot cutoff. Preserve source-document identifiers without personal absolute paths.
- Include schema/methodology version, source-code revision, immutable bundle version, file hashes, selected metrics/periods and this review reference in the manifest. Show reference dates and source links in the app.
- State: “Independent portfolio project.” Do not use SEC or MercadoLibre logos for source attribution, and do not imply endorsement, sponsorship, affiliation, or approval by either organization.

The financial Parquet schema has no source URL or retrieval-time column; place supplementary references in the manifest rather than inventing a parallel analytical schema. Existing operational provenance columns remain intact.

## Market exclusion remains in force

`market_prices` remains excluded. `market_capitalization` remains excluded while dependent on excluded prices. Twelve Data redistribution is outside this review. Nothing here approves provider payloads, price-derived Gold or price-dependent valuation multiples. Public mode must not fall back to local Market files even if present.

## Approved public snapshot contract

Decision corresponds to **outcome A for source suitability**: both current transformed source chains support the proposed snapshot. This does not authorize wholesale copying of their full production Parquets.

Keep the Sprint 8C dataset allowlist and proposed files:

- `demo_data/v1/silver/sec/financial_facts.parque
- `demo_data/v1/silver/sec/operational_kpis.parque
- `demo_data/v1/manifest.json

Use the existing 26/29-column schemas and readers. Select a fixed window of at most four completed quarters and a declared disclosure cutoff; preserve INSTANT facts as instants. Useful coverage must satisfy the existing contract's revenue/GMV/TPV history and Fintech MAU requirements, using current selectors. A recent-window inspection found multiple quarterly revenue/GMV/TPV observations and MAU snapshots; it also found incomplete quarterly OCF/capex coverage. Do not manufacture missing quarters to make coverage uniform.

The other ten optional catalog datasets may remain missing. No additional strategic, Macro, Product or extended operational artifact is approved by this review. Immutable release snapshots, explicit freshness and fail-closed public mode remain required. Public-mode implementation can proceed without any IR-only source or Market permission dependency.

## Sprint 8D implementation constraints

1. **Pin inputs before export.** Record source-file hashes, reviewed source URLs/accessions, retrieval dates and code/schema versions. The public manifest contains public-safe provenance, not raw payloads or private paths. Never run ingestion from the public app.
2. **Financial validation:** require CIK `0001099590`, the reviewed SEC Company Facts endpoint/metadata, approved concept mapping, allowed forms and exact existing schema. Verify each selected fact against pinned Company Facts observations by taxonomy, concept, unit, period, accession and value. Verify revision/first-filing fields through the existing normalization contract as well. A source-label string alone cannot approve a row.
3. **Operational validation:** require an exact E1–E7 accession/URL/document match for this release, `https` with hostname exactly `www.sec.gov`, and the reviewed CIK/archive path. Compare row and sidecar hashes to source bytes, and metadata accession/dates to the document identity. Reject missing or inconsistent provenance. Validate all contributing first-reported/revision lineage, not only the final selected row. Unknown documents require review rather than broadening the allowlist automatically.
4. **Reproduce, do not relabel.** A subset export may use existing canonical Silver after validation. If reconstruction is needed, use pinned EDGAR Bronze and the existing parser/canonicalizer in an isolated build location; never overwrite production data or change formulas. An IR-origin row cannot become approved by assigning an SEC URL. A true EDGAR rebuild must establish its own source bytes, hash and lineage.
5. **Select, do not bulk-copy.** Enumerate approved metrics, dates and provenance in the manifest and use deterministic ordering. Retain nulls, source scale, comparative status and definition versions. Respect disclosure cutoff as well as economic-period cutoff; do not backdate a later revision. Do not derive a missing quarter or blend definition families for presentation convenience.
6. **Test the boundary mechanically.** Include accepted SEC rows and rejected IR URLs, missing hashes, mismatched accession/document paths, forged SEC-like hostnames, unknown exhibits and altered input bytes. Test approved-row lineage preservation, deterministic export, exact schema and useful existing-selector coverage. No network calls are needed to run these fixture tests.
7. **Keep publication isolated.** Track only the three reviewed bundle paths; deny raw source files, hidden local fallbacks, Market artifacts and secrets. The fail-closed runtime/path-override/cache tests in Sprint 8C still apply. Default mode remains OFF; public mode must need no source credentials.
8. **Retain deployment gates.** Run full regression and populated/missing-bundle navigation, validate Linux paths/install/dependencies, preserve analytical/evidence semantics and tag integrity. A positive source decision is not certification of a deployed runtime.

## Deferred questions

IR-only reuse permission remains unresolved for material outside the inspected chains, and any new source/document family requires review. No blanket conclusion is made about expressive content, trademarks, third-party material or other jurisdictions. None of those open expansion questions blocks the narrowly defined SEC-backed numerical bundle.

Sprint 8D must still fix the exact cutoff, select eligible rows, validate all lineage, build the manifest and implement/test public isolation. Future refreshes must recheck SEC policies and observe fair access. No data has been published or generated by this review.

Validation in this sprint: full regression **544 passed, 1 deselected**. Source and entrypoint compilation, document whitespace, repository scope and production-data integrity are checked at delivery. No production/test/configuration changes, ingestion, Ruff or commit are part of this sprint.

## Final recommendation

The verified SEC Company Facts and SEC-hosted exhibit chains support the constrained, provenance-validated factual bundle. Proceed with public-mode implementation and reviewed subset assembly; retain all existing deployment and data-isolation acceptance gates.

PROCEED_TO_PUBLIC_MODE_IMPLEMENTATION
