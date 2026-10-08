"""Checked-in bundle integrity, provenance and deterministic subset export."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from meli_intelligence.ui import public_demo as demo
from meli_intelligence.query.duckdb import query_financial_facts
from meli_intelligence.query.operational import query_operational_kpis

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("public_demo_builder", ROOT / "scripts" / "build_public_demo.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_checked_in_bundle_has_only_approved_artifacts_and_metadata():
    manifest = demo.validate_bundle()
    files = {p.relative_to(demo.BUNDLE_ROOT).as_posix() for p in demo.BUNDLE_ROOT.rglob("*") if p.is_file()}
    assert files == {"manifest.json", *demo.ARTIFACTS.values()}
    assert set(manifest["datasets"]) == {"financial_facts", "operational_kpis"}
    assert manifest["excluded_datasets"] == list(demo.MARKET_EXCLUSIONS)
    assert "Market data is not part" in manifest["market_policy"]
    assert "endorsement" in manifest["attribution"]
    assert "logos" in manifest["attribution"]
    assert manifest["generated_at"] == "2026-10-07T00:00:00Z"
    assert "build_date_policy" in manifest
    for path in files:
        assert Path(path).suffix in {".json", ".parquet"}
        assert not any(token in path.casefold() for token in ("market", "twelve", "bronze", ".env", "payload", "api"))
    # Explicit Market exclusion text in the manifest is allowed; Market DATA is not.
    text = json.dumps(manifest)
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"\b[A-Za-z]:[\\/]", text)
    assert not re.search(r"api[_-]?key|password|secret|bearer\s", text, re.I)
    for dataset_id, relative in demo.ARTIFACTS.items():
        table = pq.ParquetFile(demo.BUNDLE_ROOT / relative).read()
        demo.validate_table(dataset_id, table)
        assert table.num_rows == manifest["datasets"][dataset_id]["row_count"]
        assert demo.sha256(demo.BUNDLE_ROOT / relative) == manifest["datasets"][dataset_id]["sha256"]
        for row in table.to_pylist():
            for value in row.values():
                if isinstance(value, str):
                    assert not re.search(r"\b[A-Za-z]:[\\/]|@[A-Za-z0-9.-]+\.", value)
                    assert len(value) < 300  # Identifiers/short labels, no narrative payloads.


@pytest.mark.parametrize("dataset_id,count", [("financial_facts", 30), ("operational_kpis", 20)])
def test_existing_readers_accept_public_snapshots(dataset_id, count):
    query = query_financial_facts if dataset_id == "financial_facts" else query_operational_kpis
    frame = query(parquet_path=demo.BUNDLE_ROOT / demo.ARTIFACTS[dataset_id])
    assert len(frame) == count
    assert frame.value.notna().all()
    assert frame.period_end.notna().all()
    assert set(frame.entity_cik) == {"0001099590"}
    allowed = demo.FINANCIAL_METRICS if dataset_id == "financial_facts" else demo.OPERATIONAL_METRICS
    assert set(frame.metric_id).issubset(allowed)


@pytest.mark.parametrize("field,value", [
    ("source", "Investor Relations only"),
    ("source_url", "https://investor.mercadolibre.com/release"),
    ("source_url", "https://www.sec.gov.example.org/Archives/edgar/data/1099590/release.htm"),
    ("source_content_sha256", "0" * 64),
    ("source_content_sha256", ""),
    ("accession_number", "0001099590-26-999999"),
    ("first_accession_number", "0001099590-26-999999"),
    ("source_bronze_file", "unreviewed.htm"),
    ("metric_id", "ir_only_metric"),
    ("unit", "BRL"),
])
def test_operational_row_level_provenance_rejects_unapproved_rows(field, value):
    table = pq.ParquetFile(demo.BUNDLE_ROOT / demo.ARTIFACTS["operational_kpis"]).read()
    rows = table.to_pylist()
    rows[0][field] = value
    poisoned = pa.Table.from_pylist(rows, schema=table.schema)
    with pytest.raises(ValueError):
        demo.validate_table("operational_kpis", poisoned)
    with pytest.raises(ValueError, match="approved SEC"):
        builder.assert_source_rows(poisoned, table)


@pytest.mark.parametrize("field,value", [
    ("source", "IR"), ("entity_cik", "0000000001"), ("form", "8-K"),
    ("unit", "BRL"), ("is_derived", True), ("accession_number", ""),
])
def test_financial_row_level_provenance_rejects_unapproved_rows(field, value):
    table = pq.ParquetFile(demo.BUNDLE_ROOT / demo.ARTIFACTS["financial_facts"]).read()
    rows = table.to_pylist()
    rows[0][field] = value
    with pytest.raises(ValueError):
        demo.validate_table("financial_facts", pa.Table.from_pylist(rows, schema=table.schema))


@pytest.mark.parametrize("dataset_id", tuple(demo.ARTIFACTS))
def test_duplicate_facts_rejected(dataset_id):
    table = pq.ParquetFile(demo.BUNDLE_ROOT / demo.ARTIFACTS[dataset_id]).read()
    duplicate = pa.concat_tables([table, table.slice(0, 1)])
    with pytest.raises(ValueError, match="Duplicate"):
        demo.validate_table(dataset_id, duplicate)


def test_full_column_lineage_verification_rejects_modified_values_and_revisions():
    for dataset_id in demo.ARTIFACTS:
        table = pq.ParquetFile(demo.BUNDLE_ROOT / demo.ARTIFACTS[dataset_id]).read()
        for field in ("value", "first_reported_value", "occurrences"):
            rows = table.to_pylist()
            rows[0][field] += 1
            with pytest.raises(ValueError, match="full revision lineage"):
                builder.assert_source_rows(pa.Table.from_pylist(rows, schema=table.schema), table)


@pytest.mark.parametrize("dataset_id", tuple(demo.ARTIFACTS))
def test_subset_ordering_is_deterministic_and_values_unchanged(tmp_path, dataset_id):
    table = pq.ParquetFile(demo.BUNDLE_ROOT / demo.ARTIFACTS[dataset_id]).read()
    reversed_table = pa.Table.from_pylist(list(reversed(table.to_pylist())), schema=table.schema)
    first = builder.select_snapshot(dataset_id, table)
    second = builder.select_snapshot(dataset_id, reversed_table)
    assert first.equals(second)
    assert first.to_pylist() == table.to_pylist()
    hashes = []
    for i, result in enumerate((first, second)):
        path = tmp_path / f"snapshot{i}.parquet"
        pq.write_table(result, path, compression="zstd", version="2.6", use_dictionary=True)
        hashes.append(demo.sha256(path))
    assert hashes[0] == hashes[1]
    assert hashes[0] == demo.sha256(demo.BUNDLE_ROOT / demo.ARTIFACTS[dataset_id])


def test_builder_refuses_production_or_arbitrary_output(tmp_path):
    with pytest.raises(ValueError, match="separate demo_data"):
        builder.build_bundle(tmp_path, output_root=tmp_path / "data" / "silver")
    with pytest.raises(ValueError, match="separate demo_data"):
        builder.build_bundle(tmp_path, output_root=tmp_path / "demo_data" / "v1")


def test_builder_rejects_altered_pinned_source_bytes(tmp_path):
    company = tmp_path / "data" / "bronze" / "sec" / "companyfacts" / "CIK0001099590_companyfacts.json"
    company.parent.mkdir(parents=True)
    company.write_text('{"cik":1099590}')
    company.with_suffix(".metadata.json").write_text(json.dumps({"source_url": demo.COMPANY_FACTS_URL}))
    with pytest.raises(ValueError, match="reviewed SEC snapshot"):
        builder.reviewed_sources(tmp_path / "data")
