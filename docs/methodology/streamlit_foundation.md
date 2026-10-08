# Streamlit Foundation

## Purpose and architecture

The 5A application is a local, read-only interface for MELI Intelligence. The UI is intentionally thin: canonical Parquet and existing DuckDB query modules feed a small UI data layer, then page renderers. Pages do not recalculate financial growth, macro analytics, Evidence, PESTEL, SWOT, or Product Evidence.

## Dataset catalog and data access

`meli_intelligence.ui.catalog` exposes a deterministic catalog using default paths from existing storage modules. Each spec identifies dataset, domain, layer, description, optionality, and query capability. `load_dataset` routes through an existing query API where available and otherwise reads Parquet through an in-memory DuckDB connection. It is read-only; a missing file raises at the helper boundary and the UI shows a health state. No synthetic rows or zero-value fallback are created.

Datasets cataloged: SEC financial facts; canonical and extended operational KPIs; extended operational evidence facts; Macro Silver; Macro Analytics and Macro observations; common Evidence registry and interpretations; PESTEL; SWOT; Product Evidence.

## Health and lineage

Health states are `AVAILABLE`, `MISSING`, `EMPTY`, and `INVALID`. Health checks report path, row/column counts, and the latest date from the explicit priority `reference_date`, `period_end`, `date`. Invalid data is reported without repair or deletion. Data Quality & Sources exposes existing source and lineage columns when present; URLs are displayed only if stored in the dataset.

## Filters and navigation

Shared filter state supports an allowlisted business domain plus optional start and end dates. Reversed dates and unknown domains fail validation. A filter is applied only if the dataset has the relevant column; date columns are selected in a fixed order. The current navigation contains only Executive Overview and Data Quality & Sources.

## Pages in 5A

Executive Overview reports dataset availability counts, latest reference date, and a domain/layer availability table. Data Quality & Sources lists each dataset's layer, domain, status, row/column counts, date, path, and message, with a small lineage preview for available files.

No valuation, forecasts, correlations, scores, or recommendations are shown. Later pages may cover Financial, Commerce, Fintech, Ecosystem Engagement, Macro, PESTEL, SWOT, Product Evidence, and Valuation; they are roadmap only and are not rendered in 5A.

## Runtime, cache, and portability

Run locally with `streamlit run streamlit_app.py` after installing the declared project dependencies in the user's environment. Streamlit is declared as `streamlit>=1.36`; it is absent from the current Codex Python environment and was not installed here. There is no Streamlit import in catalog, data, health, or filter helpers and no global DataFrame cache. Paths come from existing storage defaults, which derive from the installed project location rather than the current working directory. No absolute Windows repository path is embedded in production code.

Unit tests use temporary Parquet files and pure helper imports; they do not launch a browser or Streamlit server. Current limitations: the foundation presents availability and source metadata only; it does not build domain dashboards or repair invalid/missing source datasets.
