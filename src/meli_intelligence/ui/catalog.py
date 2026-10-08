"""Deterministic catalog of datasets presented by the local UI."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    display_name: str
    business_domains: tuple[str, ...]
    layer: str
    default_path: Path
    description: str
    optional: bool = True
    query_module: str | None = None
    query_function: str | None = None
    query_path_keyword: str | None = None

    @property
    def business_domain(self) -> str | tuple[str, ...] | None:
        if not self.business_domains:
            return None
        if len(self.business_domains) == 1:
            return self.business_domains[0]
        return self.business_domains

    @property
    def query_capability(self) -> str:
        if self.query_module and self.query_function:
            return f"{self.query_module}.{self.query_function}"
        return "DuckDB Parquet read"


def get_dataset_catalog() -> tuple[DatasetSpec, ...]:
    """Return specs using the storage modules' canonical default paths."""
    from meli_intelligence.storage.evidence import (
        DEFAULT_EVIDENCE_REGISTRY_PATH,
        DEFAULT_INTERPRETATIONS_PATH,
    )
    from meli_intelligence.storage.extended_operational import (
        EVIDENCE_PATH as EXTENDED_EVIDENCE_PATH,
        EXTENDED_KPI_PATH,
    )
    from meli_intelligence.storage.macro import DEFAULT_MACRO_INDICATORS_PATH
    from meli_intelligence.storage.macro_analytics import (
        DEFAULT_MACRO_ANALYTICS_PATH,
        DEFAULT_MACRO_EVIDENCE_PATH,
    )
    from meli_intelligence.storage.operational_silver import DEFAULT_OPERATIONAL_SILVER_PATH
    from meli_intelligence.storage.pestel import DEFAULT_PESTEL_PATH
    from meli_intelligence.storage.product_evidence import DEFAULT_PRODUCT_EVIDENCE_PATH
    from meli_intelligence.storage.market_prices import DEFAULT_MARKET_PRICES_PATH
    from meli_intelligence.storage.market_cap import DEFAULT_MARKET_CAP_PATH
    from meli_intelligence.storage.silver import DEFAULT_FINANCIAL_FACTS_PATH
    from meli_intelligence.storage.swot import DEFAULT_SWOT_PATH

    broad_operational_domains = ("Commerce", "Fintech", "Ecosystem", "Ads", "Logistics")
    specs = (
        DatasetSpec("market_capitalization", "Market capitalization", ("Market",), "Gold",
                    DEFAULT_MARKET_CAP_PATH, "Persisted authoritative market-cap analytics.", True,
                    "meli_intelligence.storage.market_cap", "read_market_cap_gold", "path"),
        DatasetSpec("financial_facts", "Financial facts", ("Financial",), "Silver", DEFAULT_FINANCIAL_FACTS_PATH,
                    "Canonical reported financial facts from SEC Company Facts.", True,
                    "meli_intelligence.query.duckdb", "query_financial_facts", "parquet_path"),
        DatasetSpec("market_prices", "Market prices", ("Market",), "Silver",
                    DEFAULT_MARKET_PRICES_PATH,
                    "Daily MELI market price observations from Twelve Data when locally ingested."),
        DatasetSpec("operational_kpis", "Operational KPIs", broad_operational_domains, "Silver",
                    DEFAULT_OPERATIONAL_SILVER_PATH, "Canonical operational KPIs from reported releases.", True,
                    "meli_intelligence.query.operational", "query_operational_kpis", "parquet_path"),
        DatasetSpec("extended_operational_kpis", "Extended operational KPIs", broad_operational_domains,
                    "Silver", EXTENDED_KPI_PATH, "Extended operational facts where available.", True,
                    "meli_intelligence.query.extended_operational", "query_extended_kpis", "path"),
        DatasetSpec("extended_operational_evidence", "Extended operational evidence", broad_operational_domains,
                    "Silver", EXTENDED_EVIDENCE_PATH, "Evidence facts associated with extended operational data.",
                    True, "meli_intelligence.query.extended_operational", "query_evidence", "path"),
        DatasetSpec("macro_indicators", "Macro indicators", ("Macro",), "Silver", DEFAULT_MACRO_INDICATORS_PATH,
                    "Normalized Brazilian macro indicators from official sources.", True,
                    "meli_intelligence.query.macro", "query_macro_indicators", "parquet_path"),
        DatasetSpec("macro_analytics", "Macro analytics", ("Macro",), "Gold", DEFAULT_MACRO_ANALYTICS_PATH,
                    "Derived macro analytics, separate from factual Macro Silver.", True,
                    "meli_intelligence.query.macro_analytics", "query_macro_analytics", "path"),
        DatasetSpec("macro_evidence", "Macro observations", ("Macro",), "Gold", DEFAULT_MACRO_EVIDENCE_PATH,
                    "Source-grounded macro observations.", True,
                    "meli_intelligence.query.macro_analytics", "query_macro_evidence", "path"),
        DatasetSpec("evidence_registry", "Evidence registry", (), "Gold", DEFAULT_EVIDENCE_REGISTRY_PATH,
                    "Common FACT, OBSERVATION, and INTERPRETATION registry.", True,
                    "meli_intelligence.query.evidence", "query_evidence", "path"),
        DatasetSpec("interpretations", "Interpretations", (), "Gold", DEFAULT_INTERPRETATIONS_PATH,
                    "Interpretations linked to source Evidence.", True,
                    "meli_intelligence.query.evidence", "query_interpretations", "path"),
        DatasetSpec("pestel", "PESTEL classifications", (), "Gold", DEFAULT_PESTEL_PATH,
                    "Evidence classifications across PESTEL dimensions.", True,
                    "meli_intelligence.query.pestel", "query_pestel", "path"),
        DatasetSpec("swot", "SWOT classifications", (), "Gold", DEFAULT_SWOT_PATH,
                    "Evidence-backed strategic SWOT classifications.", True,
                    "meli_intelligence.query.swot", "query_swot", "path"),
        DatasetSpec("product_evidence", "Product Evidence", ("Ecosystem",), "Gold",
                    DEFAULT_PRODUCT_EVIDENCE_PATH, "Ecosystem engagement hypotheses and discovery questions.", True,
                    "meli_intelligence.query.product_evidence", "query_product_evidence", "path"),
    )
    from meli_intelligence.ui.public_demo import public_demo_enabled, public_path

    if public_demo_enabled():
        specs = tuple(replace(spec, default_path=public_path(spec.dataset_id)) for spec in specs)
    return tuple(sorted(specs, key=lambda spec: spec.dataset_id))


def get_dataset_spec(dataset_id: str) -> DatasetSpec:
    for spec in get_dataset_catalog():
        if spec.dataset_id == dataset_id:
            return spec
    raise ValueError(f"Unknown dataset_id: {dataset_id}")


def list_dataset_ids() -> tuple[str, ...]:
    return tuple(spec.dataset_id for spec in get_dataset_catalog())
