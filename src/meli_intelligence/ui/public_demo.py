"""Static public-bundle policy. No acquisition or analytical calculations."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re

import pyarrow.parquet as pq

from meli_intelligence.config.settings import PROJECT_ROOT
from meli_intelligence.storage.silver import FINANCIAL_FACTS_SCHEMA, validate_financial_facts
from meli_intelligence.storage.operational_silver import OPERATIONAL_SCHEMA, CANONICAL_KEY

BUNDLE_ROOT = PROJECT_ROOT / "demo_data" / "v1"
ARTIFACTS = {
    "financial_facts": "silver/sec/financial_facts.parquet",
    "operational_kpis": "silver/sec/operational_kpis.parquet",
}
MARKET_EXCLUSIONS = ("market_prices", "market_capitalization")
OPTIONAL_OMISSIONS = (
    "evidence_registry", "extended_operational_evidence", "extended_operational_kpis",
    "interpretations", "macro_analytics", "macro_evidence", "macro_indicators",
    "pestel", "product_evidence", "swot",
)
REFERENCE_DATE = "2026-06-30"
DISCLOSURE_CUTOFF = "2026-10-06"
PERIOD_ENDS = ("2025-09-30", "2025-12-31", "2026-03-31", REFERENCE_DATE)
FINANCIAL_METRICS = (
    "net_revenues_financial_income", "operating_income", "net_income", "operating_cash_flow",
    "gross_profit", "capex_productive_assets", "cash_and_equivalents", "total_assets",
    "total_liabilities", "stockholders_equity",
)
INSTANT_METRICS = ("cash_and_equivalents", "total_assets", "total_liabilities", "stockholders_equity")
OPERATIONAL_METRICS = ("gmv", "unique_active_buyers", "items_sold", "fintech_mau", "tpv")
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001099590.json"
COMPANY_FACTS_HASH = "7ef80552e82d6e39c5d3d32671e5bb3fab189fd1bc486a3b1ad0671547736045"
# Exact reviewed E1-E7 document identities and source-byte hashes, not host globs.
EXHIBITS = {
    "0001099590-25-000004": ("20250220", "75fff6af04d87ce8a7dfc2fa2821f327f6c0f2f6193b376c4794177478ca46ab"),
    "0001099590-25-000025": ("20250507", "080bd267500750de7e009f6cfcd31252118f2aae5c6af6f4814a97213a990539"),
    "0001099590-25-000041": ("20250804", "31879a796e3d7e7672cc00bd4c4bde7d32cbc79b8f432bc83cc2ce3ac13af7a6"),
    "0001099590-25-000048": ("20251029", "4c3dc75d864d15a4ae6d57d0d91c1e7af47253d83809b835ed93e241e33bc66b"),
    "0001099590-26-000003": ("20260224", "e1dbf22113868795cfe8ff1fdf77fea6fc12dbc9c57d3b617bd73f09fdb18bd4"),
    "0001099590-26-000014": ("20260507", "7b81da4c2f29ad7b188e8859bd53559950b89a1990334f73d9069f039a0dc264"),
    "0001099590-26-000021": ("20260805", "e8d9199d1c5a3eef1214f2db731837b52a4a2a6847bd1df5b8baebb6cb047b87"),
}


class PublicDemoExcluded(FileNotFoundError):
    """An intentional policy omission, distinct from a broken approved artifact."""


def public_demo_enabled() -> bool:
    value = os.getenv("MELI_PUBLIC_DEMO", "0").strip().casefold()
    if value in {"0", "false", "no"}:
        return False
    if value in {"1", "true", "yes"}:
        return True
    raise ValueError("MELI_PUBLIC_DEMO must be 0/false/no or 1/true/yes.")


def omission_reason(dataset_id: str) -> str:
    if dataset_id in MARKET_EXCLUSIONS:
        return "Unavailable in this public demo: Market data and price-derived valuation are intentionally excluded; redistribution has not been cleared."
    return "Intentionally unavailable in this public demo: this dataset is outside the curated Company snapshot."


def public_path(dataset_id: str) -> Path:
    """Catalog display path only; omitted paths are never inspected or opened."""
    return BUNDLE_ROOT / ARTIFACTS.get(dataset_id, f"unavailable/{dataset_id}.parquet")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contained_path(root: Path, relative: str) -> Path:
    lexical = root.absolute() / relative
    resolved = lexical.resolve()
    if resolved != lexical or not resolved.is_relative_to(root.absolute()):
        raise ValueError("Public bundle paths must not traverse links or escape the bundle.")
    return resolved


def validate_table(dataset_id: str, table) -> None:
    """Check existing typed schemas and the approved factual selection boundary."""
    if dataset_id not in ARTIFACTS:
        raise ValueError("Dataset is not approved for the public bundle.")
    schema = FINANCIAL_FACTS_SCHEMA if dataset_id == "financial_facts" else OPERATIONAL_SCHEMA
    if not table.schema.equals(schema, check_metadata=False) or not table.num_rows:
        raise ValueError("Public artifact must be nonempty and match its existing Silver schema.")
    if any(not field.nullable and table[field.name].null_count for field in schema):
        raise ValueError("Public artifact has null required fields.")
    rows = table.to_pylist()
    for row in rows:
        if row["entity_cik"] != "0001099590" or row["entity_name"] != "MercadoLibre, Inc.":
            raise ValueError("Unexpected public Company identity.")
        if row["period_end"].isoformat() not in PERIOD_ENDS:
            raise ValueError("Observation is outside the static snapshot.")
        instant = row["metric_id"] in INSTANT_METRICS if dataset_id == "financial_facts" else row["metric_id"] == "fintech_mau"
        if row["period_type"] != ("INSTANT" if instant else "QUARTER"):
            raise ValueError("Only existing quarterly and instant snapshot facts are allowed.")
        if instant:
            if row["period_start"] is not None:
                raise ValueError("Instant fact has a duration start.")
        else:
            end = row["period_end"]
            if row["period_start"] != end.replace(month=end.month - 2, day=1):
                raise ValueError("Quarter must retain its exact reported duration.")
        if row["reference_year"] != row["period_end"].year or not math.isfinite(row["value"]):
            raise ValueError("Invalid reference year or numerical value.")
        if dataset_id == "financial_facts":
            if (row["source"] != "SEC EDGAR Company Facts API" or row["taxonomy"] != "us-gaap"
                    or row["metric_id"] not in FINANCIAL_METRICS or row["form"] not in {"10-K", "10-Q"}
                    or row["is_derived"] or row["filed_at"].isoformat() > DISCLOSURE_CUTOFF):
                raise ValueError("Unapproved financial provenance.")
            for key in ("accession_number", "first_accession_number"):
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", row[key] or ""):
                    raise ValueError("Missing financial filing lineage.")
        else:
            accession = row["accession_number"]
            if accession not in EXHIBITS or row["first_accession_number"] not in EXHIBITS:
                raise ValueError("Unapproved operational accession lineage.")
            stamp, digest = EXHIBITS[accession]
            filename = f"meli-{stamp}xex991.htm"
            expected_url = f"https://www.sec.gov/Archives/edgar/data/1099590/{accession.replace('-', '')}/{filename}"
            if (row["source"] != "SEC EDGAR earnings release exhibit" or row["metric_id"] not in OPERATIONAL_METRICS
                    or row["source_url"] != expected_url or row["source_content_sha256"] != digest
                    or row["source_bronze_file"] != f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}_{accession.replace('-', '')}_{filename}"
                    or row["filing_date"].isoformat() > DISCLOSURE_CUTOFF):
                raise ValueError("Unapproved operational source document.")
            expected_unit = {"gmv": "USD", "tpv": "USD", "fintech_mau": "users", "unique_active_buyers": "users", "items_sold": "items"}[row["metric_id"]]
            if row["unit"] != expected_unit or not row["definition_version"]:
                raise ValueError("Invalid operational units or definition.")
    if dataset_id == "financial_facts":
        validate_financial_facts(rows)
        keys = ("metric_id", "unit", "period_start", "period_end")
    else:
        keys = CANONICAL_KEY
    identities = [tuple(row[key] for key in keys) for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate public economic facts.")


def validate_bundle(root: Path | None = None) -> dict:
    """Fail closed on the complete immutable bundle; never inspect production data."""
    root = root or BUNDLE_ROOT
    manifest_path = _contained_path(root, "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("bundle_id") != "v1" or manifest.get("contract_version") != "1"
            or manifest.get("snapshot_reference_date") != REFERENCE_DATE
            or manifest.get("snapshot_cutoff") != DISCLOSURE_CUTOFF
            or set(manifest.get("datasets", {})) != set(ARTIFACTS)
            or manifest.get("excluded_datasets") != list(MARKET_EXCLUSIONS)
            or manifest.get("intentionally_missing_datasets") != list(OPTIONAL_OMISSIONS)):
        raise ValueError("Public manifest does not match the approved release contract.")
    expected_files = {"manifest.json", *ARTIFACTS.values()}
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual_files != expected_files:
        raise ValueError("Public bundle contains missing or unapproved artifacts.")
    for dataset_id, relative in ARTIFACTS.items():
        entry = manifest["datasets"][dataset_id]
        if entry.get("path") != relative or entry.get("schema_version") != "1":
            raise ValueError("Public manifest path/schema mismatch.")
        artifact = _contained_path(root, relative)
        if sha256(artifact) != entry.get("sha256"):
            raise ValueError("Public artifact checksum mismatch.")
        table = pq.ParquetFile(artifact).read()
        validate_table(dataset_id, table)
        rows = table.to_pylist()
        if (len(rows) != entry.get("row_count")
                or sorted({r["metric_id"] for r in rows}) != entry.get("metric_ids")
                or sorted({r["accession_number"] for r in rows}) != entry.get("accessions")
                or sorted({r["first_accession_number"] for r in rows}) != entry.get("first_accessions")
                or entry.get("source_family") != rows[0]["source"]
                or entry.get("source_organization") != "MercadoLibre, Inc."):
            raise ValueError("Public manifest coverage mismatch.")
        if dataset_id == "financial_facts":
            provenance = entry.get("provenance", {})
            if provenance.get("source_url") != COMPANY_FACTS_URL or provenance.get("content_sha256") != COMPANY_FACTS_HASH:
                raise ValueError("Public financial source input is not approved.")
        else:
            documents = entry.get("provenance", {}).get("documents", [])
            if len(documents) != len(EXHIBITS) or {d.get("accession_number") for d in documents} != set(EXHIBITS):
                raise ValueError("Public exhibit provenance set is not approved.")
            for document in documents:
                accession = document["accession_number"]
                stamp, digest = EXHIBITS[accession]
                url = f"https://www.sec.gov/Archives/edgar/data/1099590/{accession.replace('-', '')}/meli-{stamp}xex991.htm"
                if document.get("content_sha256") != digest or document.get("source_url") != url:
                    raise ValueError("Public exhibit provenance mismatch.")
    return manifest


def resolve_dataset_path(dataset_id: str, local_path: Path, override=None) -> Path:
    if not public_demo_enabled():
        return Path(override if override is not None else local_path)
    if dataset_id not in ARTIFACTS:
        raise PublicDemoExcluded(omission_reason(dataset_id))
    expected = _contained_path(BUNDLE_ROOT, ARTIFACTS[dataset_id])
    if override is not None and Path(override).absolute() != expected:
        raise PermissionError("Public mode accepts only the approved demo path.")
    # Give missing core artifacts an explicit missing state before whole-bundle validation.
    if not expected.is_file():
        raise FileNotFoundError("Approved public-demo artifact is missing; no local fallback.")
    validate_bundle()
    return expected


def render_public_demo_notice(st) -> None:
    if public_demo_enabled():
        st.info(
            f"Portfolio demo mode · static curated snapshot through {REFERENCE_DATE} (v1). "
            "Partial coverage: Company financials, Commerce and Fintech. Market data is intentionally excluded. "
            "Other domains may be intentionally unavailable."
        )
        st.caption("Sources: MercadoLibre disclosures via SEC EDGAR. Independent portfolio project; no SEC or MercadoLibre endorsement or affiliation.")
