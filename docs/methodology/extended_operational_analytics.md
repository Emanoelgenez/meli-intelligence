# Extended Operational Analytics and Evidence Normalization

## Extended KPI analytics

Derived metrics use the structured extended operational facts for AUM,
total credit portfolio and total-portfolio 15-90 day NPL, plus reported
Fintech MAU from Operational Silver. Every output retains its metric ID,
period metadata, unit, formula, source metrics, derivation flag,
methodology version and input qualifier/scope context.

### Year-over-year comparability

YoY comparisons require a prior observation exactly one calendar year
earlier, with the same month and day, period type, period label, unit and
scope. Missing periods are not interpolated. Duplicate source keys fail
explicitly as ambiguous.

AUM and credit-portfolio growth use:

`(current_value / previous_year_value - 1) * 100`

Both values must have `value_qualifier = exact`. Approximate and
lower-bound values are excluded. A quoted USD amount in billions may be
rounded in the release, so derived growth can differ slightly from
management's published YoY rate. In particular, the Q2 2026 credit
portfolio disclosure “surpassed $16bn” remains a lower bound and produces
no YoY growth.

NPL is a percentage, so its YoY movement is an absolute difference in
percentage points:

`current_npl_percent - previous_year_npl_percent`

Only total-portfolio NPL is used. A missing period, including Q4 2025,
stays absent; credit-card NPL is never substituted.

### Per-user snapshot ratios

AUM or credit portfolio per Fintech MAU is calculated only when the
extended fact and reported MAU have exactly the same `period_end`, both
are `INSTANT` snapshots, the numerator unit is `USD`, the MAU unit is
`users`, and the extended value is exact. MAU must be positive. When the
operational input provides `definition_version`, it is retained in the
derived metric's definition context. No nearby period is used as a
proxy. Q2 2026 credit portfolio per MAU is absent because its
credit-portfolio input is a lower bound. These are descriptive ratios,
not causal statements or company-reported KPIs.

## FACT to OBSERVATION

V1 normalizes each evidence FACT into one OBSERVATION. It preserves the
source statement with whitespace normalization only, alongside the
source URL, filing date, accession number and reference period. Evidence
types map deterministically to Ecosystem (`meli_plus`,
`ecosystemic_users`), Ads (`advertising`) and Logistics (`fulfillment`).
Observation IDs are stable SHA-256 hashes of evidence IDs.

An optional `claim_kind` is assigned only by explicit lexical rules when
exactly one class matches: growth, share, engagement or operational.
Growth words such as `up` are accepted only in an explicit numeric
change construction, such as “up by 15”, “up 72% YoY” or “up 8ppts”;
phrases such as “up to 90 days” do not count as growth. Overlapping or
unclear signals use `other`. It does not rewrite the statement or
introduce additional facts.

The implemented pipeline ends at OBSERVATION. V1 does not generate
interpretation, hypothesis, Product Discovery question, recommendation,
causal claim, ecosystemic-user estimate, engagement index or artificial
combination of MELI+, Ads, Logistics and ecosystemic users. Later stages
require separate methods and evidence.
