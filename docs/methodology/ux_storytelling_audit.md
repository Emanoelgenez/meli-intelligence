# Sprint 8A — UX and storytelling audit

## Scope and method

This is a **heuristic expert review, not a usability study**. It uses source inspection and offline render-contract tests with synthetic inputs. It does not establish user-testing validation, WCAG conformance, measured contrast, screen-reader compatibility or verified browser layouts. No HTTP requests or production-data writes are part of this review.

Baseline: `ee9f3eaac5eca4bcbec5477a9817febb41d84589`. The existing `v1.0.0` tag is outside the change scope.

Reviewed: `streamlit_app.py`; UI catalog, data, health, filters, presentation and storytelling helpers; all ten navigation pages; `test_streamlit_*.py`; `dashboard_storytelling_ux.md`; README terminology. The older dashboard document describes its original sprint; current page code is the evidence for this review.

Severity describes the baseline: **PASS** = adequate within inspected scope; **MINOR** = clarity/layout opportunity; **SHOULD_FIX** = material communication gap; **BLOCKER** = unsafe or unusable core flow demonstrated by this review. No blocker was identified within this inspection scope.

## Nielsen's 10 heuristics

| Heuristic | Current evidence at baseline | Classification | Proposed action | Implemented in 8A |
| --- | --- | --- | --- | --- |
| 1. Visibility of system status | Health codes and reference dates are visible. In `valuation_storytelling.render`, early returns bypass the TTM/P/E scope caption. | SHOULD_FIX | Put scope limits before all return paths; retain unavailable reasons. | Yes: F1. |
| 2. Match between system and real world | Most metric labels use business language; Commerce/Fintech use “Reported trajectory” and Macro uses “Primary time series.” | MINOR | Name the existing measure in the chart heading without asserting a trend conclusion or unsupported frequency. | Yes: F3. |
| 3. User control and freedom | Sidebar navigation, dates and Reset filters are present. Domain pages intentionally ignore the global business-domain selection, but only Product explicitly explains this in the sidebar. | MINOR | Clarify filter applicability in a later navigation pass without altering filter semantics. | Deferred: D1. |
| 4. Consistency and standards | Shared date/status formatters exist; Market, Product and valuation-input unavailable copy varies in explanation and recovery direction. | SHOULD_FIX | Share state → reason → non-fabrication boundary wording, preserving domain-specific limits. | Yes: F2 in these three views; no mechanical rewrite of all pages. |
| 5. Error prevention | Date validation and read-only page access exist; selectors retain explicit eligibility and schema checks. | PASS | Preserve validation, selection and backend ownership. | Retained; no logic change. |
| 6. Recognition rather than recall | Metric labels, source/precision expanders, lineage and dated records reduce reliance on remembered IDs. | PASS | Preserve labels, source and date context. | Retained. |
| 7. Flexibility and efficiency of use | Filters, bounded previews and expanders support scanning. Up to four metric columns and long labels need narrow-viewport review. | MINOR | Preserve native layout; separate the combined P/S and P/Operating Cash Flow missing explanation; defer broad card-layout changes. | Partial: F4; D2 deferred. |
| 8. Aesthetic and minimalist design | Most pages follow context → evidence → visual → existing interpretation → details. Repeated missing sections and dense source/status text remain. | MINOR | Keep primary limits visible, technical lineage in expanders; avoid blanket copy removal that hides uncertainty. | Partial: F1/F4; D2/D3 deferred. |
| 9. Help users recognize, diagnose and recover from errors | Statuses are textual, but Product missing state lacks a route to source diagnostics and some views state a code without explaining it. | SHOULD_FIX | Add plain-language reasons and a consistent Data Quality & Sources pointer without fetch/repair instructions. | Yes: F2. |
| 10. Help and documentation | Methodology expanders, Data Quality & Sources, README and methodology notes document scope and lineage. | PASS | Retain technical details and add this review with explicit validation limits. | Yes: audit added; existing help retained. |

Matrix totals: **3 PASS, 4 MINOR, 3 SHOULD_FIX, 0 BLOCKER**. Rows can refer to the same finding; these are heuristic ratings, not counts of distinct defects.

## Storytelling assessment

| Dimension | Assessment and disposition |
| --- | --- |
| Context before metrics | PASS: overview/domain questions precede facts; Product's opening now explicitly says hypotheses are not validated Product problems (F1). |
| Visual hierarchy | MINOR: existing hierarchy is sound; valuation scope now precedes every availability branch. Dense metric rows remain a viewport-review item (D2). |
| Message clarity | MINOR: F2 expands opaque unavailable codes into an explanation and boundary. Existing stored claims remain verbatim. |
| Evidence vs interpretation | PASS: FACT/OBSERVATION/INTERPRETATION remain distinct; UI selects stored interpretations and does not derive takeaways from charts. |
| Explicit uncertainty | SHOULD_FIX: F1 keeps TTM/P/E limits visible even when valuation inputs are missing or invalid; Product uncertainty is stated before records. |
| Empty-state quality | SHOULD_FIX: F2 makes Market/Product/valuation-input states consistent and diagnostic. No hypotheses, prices or input values are synthesized. |
| Cognitive load | MINOR: F4 separates two long unavailable ratio labels. Existing detailed lineage remains in expanders; broad density work is deferred (D2/D3). |
| Chart-title usefulness | MINOR: F3 replaces generic Commerce, Fintech and Macro headings with factual metric names. Financial and Market headings already identify the series. No acceleration, causality or engagement conclusion is added. |
| Source/date visibility | PASS with minor opportunity: economic/trading dates remain visible; many source labels are in expanders. Their visibility and long-label wrapping need browser review (D3). Retrieval timestamps remain technical provenance. |
| Analytical boundaries | PASS: Company, Market and Product remain separate. F1 surfaces the existing Market-to-Product non-inference boundary before the price section. MELI34 and valuation contracts are unchanged. |
| Next question without recommendation | PASS: overview points to source inspection; Product shows only persisted discovery questions. No generic “So what?” block, new conclusion or recommendation is generated. |

## Implemented findings

- **F1 — Visible limitations (SHOULD_FIX):** move the existing valuation TTM/P/E caption before early returns. State the existing Product hypothesis boundary in its opening and the Market/user-behavior boundary before price evidence. No analytical claim or eligibility rule changes.
- **F2 — Unavailable messages (SHOULD_FIX):** add `presentation.unavailable_message` for dataset states in Market, Product Evidence and valuation inputs. Include an explicit text status, known state explanation, domain-specific non-fabrication boundary and Data Quality & Sources pointer. Unknown reasons remain unknown. Backend valuation reasons are not rewritten.
- **F3 — Factual chart headings (MINOR):** Commerce/Fintech headings use the existing `trend_spec.display_name`; Macro names Target Selic and its already documented daily observations. No quarterly assumption is introduced for operational series.
- **F4 — Long ratio explanations (MINOR):** split the combined no-snapshot P/S and P/Operating Cash Flow message into two native full-width information blocks. Keep the existing reason text. Snapshot-derived reasons retain their original full-width blocks and verbatim content.

## Accessibility and responsive-layout review

| Concern | Source-level evidence and action | Verification limit |
| --- | --- | --- |
| Color-independent meaning | State codes and plain-language labels remain visible; no red/green performance convention or symbol-only status added. | Render tests verify text, not theme contrast. |
| Readable hierarchy | Native titles, subheaders, captions and information blocks; essential valuation/Product limitations remain outside expanders. | Browser typography and zoom are not measured. |
| Valuation and long ratio names | Existing valuation uses a vertical flow, not metric columns. F4 separates the combined label; reasons are not stored as metric values or restricted by fixed widths. | Full-width call structure tested; pixel wrapping not certified. |
| Metric columns and source/status labels | Overview, Financial, Commerce/Fintech and Macro can use four columns. Product uses three summary columns; SWOT uses two narrative columns. Source/lineage tables use stretch width. | D2/D3: test narrow widths before redesign; no font shrinking or custom CSS introduced. |
| Right-edge chart labels | Native line charts use semantic date/value axes; no manual edge annotations or fixed pixel widths found in the reviewed chart calls. | Actual tick clipping at narrow widths remains unverified (D2). |
| Keyboard and assistive technology | Native navigation, filters and expanders retained. | Keyboard order, focus behavior and screen-reader output require an interactive review (D4). |

## Deferred work

- **D1:** explain business-domain filter applicability across pages. Preserve current behavior until a focused navigation review defines the copy consistently.
- **D2:** inspect desktop and narrow/mobile widths (including zoom), long metric values, four-column rows and right-edge chart ticks. No claim of responsive-layout certification; changing every layout without rendered evidence would exceed this small polish pass.
- **D3:** review repeated empty-section density and source/status/lineage readability, especially Data Quality & Sources. Keep diagnostic detail available; avoid removing important uncertainty to shorten pages.
- **D4:** interactive keyboard, screen-reader and contrast checks, followed by actual user research. Native widgets alone do not prove accessibility or usability.

## Preserved contracts and validation

Evidence discipline remains FACT → OBSERVATION → INTERPRETATION → PESTEL / SWOT → HYPOTHESIS → QUESTION_FOR_PRODUCT_DISCOVERY. Correlation does not imply causation. Product hypotheses are not validated Product problems. Market price does not explain user behavior. No source contracts, financial selectors, valuation calculations or evidence methodology are changed.

P/S and P/Operating Cash Flow remain unavailable without valid TTM contracts; P/E remains outside scope. No Buy/Sell/Hold, target price, fair value or trading recommendation is introduced. Data, ingestion, storage, transformations and analytics remain outside the edit scope.

Offline tests cover shared message behavior, absent/empty/invalid data, visible limitations on early returns, verbatim backend unavailable reasons, factual chart headings, unchanged plotted observations, preserved Product statements and all navigation pages with missing datasets. Tests use synthetic inputs and a recording UI; they do not constitute a visual browser review. Required regression, compilation, diff, data-manifest and tag checks are reported at sprint delivery.
