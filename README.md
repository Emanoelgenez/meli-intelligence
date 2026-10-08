# MELI Intelligence

MELI Intelligence is a local analytical application for MercadoLibre, Inc. It organizes company financial facts, operating KPIs, Brazilian macro context and market observations into traceable datasets and a Streamlit UI.

The project addresses the gap between fragmented public disclosures and structured analysis: readers can follow a reported fact through analytical observations and strategic synthesis to questions for Product Discovery, while retaining source, period and definition boundaries.

## MVP status

The local product/analytics MVP includes Company fundamentals, operational KPIs, Commerce / Fintech storytelling, macro context, PESTEL, SWOT, Product Evidence, Market data, persisted Market Cap Gold, valuation context and a Streamlit analytical UI. It is a local research and portfolio application; production SaaS readiness is outside its scope.

Dataset availability depends on separately populated local files. Starting the application does not ingest or refresh sources. Missing, empty or invalid datasets are surfaced as health states rather than replaced with invented values.

## Architecture

```text
SOURCE → INGESTION → BRONZE → VALIDATION → SILVER
       → ANALYTICS → GOLD → DUCKDB / QUERY → STREAMLIT
```

- **Bronze:** source payloads and retrieval/provenance metadata retained for auditability.
- **Silver:** validated, normalized financial facts, operating KPIs, macro indicators and market observations, stored in typed Parquet datasets.
- **Gold:** derived analytics and structured evidence, interpretations, strategic classifications, Product hypotheses/questions and market capitalization, with lineage to their inputs.

Python source clients and pipelines handle acquisition and transformation. DuckDB/query helpers read local datasets; the Streamlit presentation layer consumes Silver and Gold without performing ingestion. This is a logical data flow, not an automatically scheduled refresh service.

## Analytical boundaries

### Company

MercadoLibre, Inc. is the corporate entity. Company financial facts and operating KPIs come from authoritative Company disclosures and SEC filings. Periods, units, filing dates and metric definitions constrain comparability.

### Market

MELI stock observations are a separate market-data layer. Current daily ingestion covers MELI in USD. MELI34 is market context only: it is not assigned separate Company fundamentals, and MELI34 ingestion or BDR parity conversion is not implemented.

### Product

Product Evidence consumes business evidence and structured synthesis to produce hypotheses and discovery questions. Aggregate buyers, Fintech MAU, GMV and TPV do not establish individual engagement, cross-domain user overlap or retention. Market prices and valuation must not be used to infer user engagement or Product behavior.

## Sources

| Authority / provider | Role |
| --- | --- |
| MercadoLibre Investor Relations | Official Company earnings releases and operating disclosures. |
| SEC / EDGAR | Structured Company Facts and filed disclosures, including operational-release exhibits; authoritative financial and eligible shares-outstanding inputs. |
| Banco Central do Brasil | Official Brazilian monetary, FX, credit, activity and Pix context. |
| IBGE / SIDRA | Official Brazilian inflation, employment and retail context. |
| Twelve Data | Provider of daily MELI market observations; separate from Company facts. |

Reported Company / SEC facts and official macro statistics form the source layer. Calculations and interpretations are derived evidence, not substitute source facts. Market observations retain provider provenance. Coverage and refresh are source-specific and controlled through ingestion pipelines; not every dataset is automatically refreshed.

## Running locally

Use Python **3.11 or later**. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m streamlit run streamlit_app.py
```

Edit the local `.env` with your own source configuration before making source requests. Do not commit it. Installation uses the dependencies declared in `pyproject.toml`; the development extra includes the test tools.

A fresh checkout can run the UI and offline tests, but does not reproduce an owner's populated dashboards without the corresponding local datasets. The UI reads canonical paths from the dataset catalog in `src/meli_intelligence/ui/catalog.py`. Acquisition/build routines live in `src/meli_intelligence/pipelines/`; consult the source-specific [methodology notes](docs/methodology/) before preparing data. There is no single documented command that rebuilds every domain end to end. Credentials alone do not populate the UI.

## Environment variables

For the curated portfolio snapshot, set `$env:MELI_PUBLIC_DEMO = "1"` in PowerShell before running `python -m streamlit run streamlit_app.py`. Set it to `"0"` for the existing local mode. Public mode reads only the reviewed static Company artifacts in `demo_data/v1/`; Market and other omitted domains remain explicitly unavailable. It requires no source credentials and performs no ingestion. The banner and Data Quality page disclose the static reference date and partial coverage.

The offline builder is `scripts/build_public_demo.py`; its `--source-data` argument must identify an existing reviewed source snapshot. It makes no network requests, validates SEC provenance, and exports a deterministic subset rather than copying production files. New source inputs or releases require review under [public source review](docs/methodology/public_source_review.md).

Project settings load the repository-root `.env` via `python-dotenv`. Existing process environment values take precedence. Keep credentials and contact identifiers local.

| Variable | Requirement and purpose |
| --- | --- |
| `MELI_PUBLIC_DEMO` | Defaults OFF; `0` / `false` / `no` select existing local mode, `1` / `true` / `yes` select the static portfolio bundle. Other values fail explicitly. |
| `SEC_USER_AGENT` | Required for SEC requests unless supplied explicitly by the caller. Replace the example placeholder with a descriptive application/contact identifier suitable for SEC requests. |
| `TWELVE_DATA_API_KEY` | Required for Twelve Data fetches unless supplied explicitly by the caller. The example is empty; set your own provider key locally. |
| `LOG_LEVEL` | Retained in `.env.example` with the safe value `INFO`, but current production code does not read it. It is not an active logging configuration control. |

Source credentials are not needed to read already prepared local datasets or run the default offline test suite. Do not use the example SEC placeholder for live requests.

## Tests

```powershell
python -m pytest
python -m compileall src
python -m py_compile streamlit_app.py
```

At MVP closeout, the validated regression baseline was **510 passed, 1 deselected**. This records that closeout state, not a permanent test-count guarantee. The default pytest configuration excludes tests marked `integration`, which call external services; unit tests use local fixtures and mocked source transports.

## Methodology and evidence

```text
FACT → OBSERVATION → INTERPRETATION → PESTEL / SWOT
     → HYPOTHESIS → QUESTION_FOR_PRODUCT_DISCOVERY
```

A fact preserves a reported value or statement; an observation describes supported evidence; an interpretation is explicitly labeled and linked to its inputs. PESTEL and SWOT provide structured classifications where applicable, not mandatory stages for every record. Product outputs retain evidence lineage and compatible periods/definitions.

**Correlation does not imply causation.** Product hypotheses are not automatically treated as validated Product problems, confirmed user behavior, solutions or prioritization decisions. Missing eligible evidence can legitimately yield no hypothesis.

See [evidence synthesis](docs/methodology/evidence_synthesis.md), [Product Evidence](docs/methodology/product_evidence.md) and the broader [methodology directory](docs/methodology/). Some notes record earlier sprint scope; the MVP status above reflects the current application.

## Valuation scope

- Persisted **MELI/USD Market Cap Gold** combines an exact market close with an eligible authoritative SEC shares-outstanding fact, preserving provenance and filing-date eligibility.
- **P/B** is supported when an available Market Cap Gold observation and positive, authoritative, eligible book value exist.
- **P/S** remains unavailable until a valid trailing-twelve-month (TTM) revenue denominator contract exists.
- **P/Operating Cash Flow** remains unavailable until valid TTM operating cash flow exists.
- **P/E** is outside the current scope.

Quarterly revenue or cash flow is not silently annualized into TTM. Missing or incompatible inputs produce explicit unavailable states rather than zero-valued multiples. These outputs provide context and do not classify the stock as cheap or expensive. See [Market Cap methodology](docs/methodology/market_cap_foundation.md) and [valuation methodology](docs/methodology/valuation_foundation.md).

## Repository structure

| Path | Contents |
| --- | --- |
| `src/meli_intelligence/` | Source clients, pipelines, transformations, storage, analytics, evidence, strategy, Product, query and UI modules. |
| `data/` | Local Bronze, Silver and Gold artifacts; generated datasets are intentionally excluded from version control. |
| `docs/methodology/` | Source contracts, metric definitions, evidence rules and domain boundaries. |
| `tests/` | Unit regression tests and separately marked integration tests. |
| `streamlit_app.py` | Streamlit application entrypoint and navigation. |

## Data and licensing

Third-party market-data use and redistribution are subject to the provider's terms and licensing. Local ingestion or internal analysis does not establish permission to redistribute data publicly or expose it in a hosted demo. Review the applicable terms before sharing datasets or deploying a public data view.

Repository-local generated data and databases may be intentionally excluded from version control; local production `data/` is not a distributable fixture set. `.env` is ignored, while `.env.example` contains only placeholders/default-safe values. A software license has not yet been selected; this README makes no open-source license claim.

## MVP limitations

The current scope does not aim to provide:

- Real-time streaming, trading prediction or ML forecasting.
- Buy/Sell/Hold recommendations, target prices or fair-value recommendations.
- Peer valuation comparison or fully implemented TTM valuation denominators.
- Cloud deployment, authentication or production SaaS operations.
- Generic scraping or automatic refresh of every dataset.
- Causality claims or user-level Product behavior inferred from aggregate business or market data.

These are intentional scope boundaries. Local coverage, source availability and provider limits determine which evidence is available for analysis.
