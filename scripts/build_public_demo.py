"""Offline, deterministic export of the reviewed SEC-backed portfolio snapshot.

Run from a source-tree installation with:
`python scripts/build_public_demo.py --source-data PATH`.
The source is read only. No HTTP, source acquisition, or production writes.
"""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from meli_intelligence.analytics.financial import calculate_yoy_growth as financial_yoy
from meli_intelligence.analytics.operational import (
    calculate_yoy_growth as operational_yoy,
)
from meli_intelligence.storage.operational_silver import (
    OPERATIONAL_SCHEMA,
    _prepare,
    canonicalize_operational_rows,
)
from meli_intelligence.storage.silver import FINANCIAL_FACTS_SCHEMA, _prepare_rows
from meli_intelligence.transformations.operational_kpis import parse_operational_release
from meli_intelligence.transformations.sec_companyfacts import normalize_company_facts
from meli_intelligence.ui.public_demo import (
    ARTIFACTS,
    BUNDLE_ROOT,
    COMPANY_FACTS_HASH,
    COMPANY_FACTS_URL,
    CONTRACT_VERSION,
    DISCLOSURE_CUTOFF,
    EXHIBITS,
    FINANCIAL_METRICS,
    HISTORY_POLICY_VERSION,
    INSTANT_METRICS,
    MARKET_EXCLUSIONS,
    OPERATIONAL_METRICS,
    OPTIONAL_OMISSIONS,
    REFERENCE_DATE,
    REFERENCE_DATE_VALUE,
    _contained_path,
    coverage_by_metric,
    sha256,
    validate_bundle,
    validate_table,
)

CODE_REVISION = "06b9d96e600995de971ab713e37c8705ee6c5e26"


def assert_source_rows(table, expected) -> None:
    """Compare every column, including complete revision lineage."""
    if not table.schema.equals(expected.schema, check_metadata=False):
        raise ValueError(
            "Source Silver schema differs from its approved reconstruction."
        )
    expected_rows = {
        json.dumps(r, sort_keys=True, default=str) for r in expected.to_pylist()
    }
    rows = [json.dumps(r, sort_keys=True, default=str) for r in table.to_pylist()]
    if len(set(rows)) != len(rows) or not set(rows).issubset(expected_rows):
        raise ValueError(
            "Source rows differ from approved SEC facts or full revision lineage."
        )


def reviewed_sources(source_data: Path) -> tuple[dict, dict]:
    """Reconstruct lineage in memory without pipeline or writer calls."""
    company = (
        source_data
        / "bronze"
        / "sec"
        / "companyfacts"
        / "CIK0001099590_companyfacts.json"
    )
    metadata = json.loads(
        company.with_suffix(".metadata.json").read_text(encoding="utf-8")
    )
    if (
        sha256(company) != COMPANY_FACTS_HASH
        or metadata.get("source_url") != COMPANY_FACTS_URL
        or metadata.get("source") != "SEC EDGAR Company Facts API"
    ):
        raise ValueError("Company Facts input is not the reviewed SEC snapshot.")
    payload = json.loads(company.read_text(encoding="utf-8"))
    if (
        str(payload["cik"]).zfill(10) != "0001099590"
        or payload["entityName"] != "MercadoLibre, Inc."
    ):
        raise ValueError("Unapproved Company Facts entity.")
    financial = pa.Table.from_pylist(
        _prepare_rows(
            normalize_company_facts(payload),
            entity_cik="0001099590",
            entity_name=payload["entityName"],
        ),
        schema=FINANCIAL_FACTS_SCHEMA,
    )
    release_dir = source_data / "bronze" / "sec" / "operational_releases"
    expected_names = set()
    rows = []
    source_documents = []
    for accession, (stamp, digest) in EXHIBITS.items():
        filename = f"meli-{stamp}xex991.htm"
        bronze_name = (
            f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}_"
            f"{accession.replace('-', '')}_{filename}"
        )
        expected_names.add(bronze_name)
        path = release_dir / bronze_name
        sidecar = json.loads(
            Path(str(path) + ".metadata.json").read_text(encoding="utf-8")
        )
        url = (
            "https://www.sec.gov/Archives/edgar/data/1099590/"
            f"{accession.replace('-', '')}/{filename}"
        )
        filing = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
        if (
            sha256(path) != digest
            or sidecar.get("content_sha256") != digest
            or sidecar.get("accession_number") != accession
            or sidecar.get("source_url") != url
            or sidecar.get("source") != "SEC EDGAR earnings release exhibit"
            or sidecar.get("filing_date") != filing
        ):
            raise ValueError("Operational document identity/hash is not approved.")
        parsed = parse_operational_release(path.read_bytes(), sidecar)
        for row in parsed:
            row.update(
                entity_cik="0001099590",
                entity_name="MercadoLibre, Inc.",
                source="SEC EDGAR earnings release exhibit",
                source_bronze_file=bronze_name,
                source_content_sha256=digest,
            )
        rows.extend(parsed)
        source_documents.append(
            {
                "accession_number": accession,
                "source_url": url,
                "source_document": filename,
                "content_sha256": digest,
                "retrieved_at": sidecar["retrieved_at"],
                "filing_date": filing,
            }
        )
    if {p.name for p in release_dir.glob("*.htm")} != expected_names:
        raise ValueError(
            "Unreviewed operational source documents require a new source review."
        )
    import pandas as pd

    operational = pa.Table.from_pandas(
        _prepare(canonicalize_operational_rows(pd.DataFrame(rows))),
        schema=OPERATIONAL_SCHEMA,
        preserve_index=False,
    )
    tables = {"financial_facts": financial, "operational_kpis": operational}
    provenance = {
        "financial_facts": {
            "source_url": COMPANY_FACTS_URL,
            "content_sha256": COMPANY_FACTS_HASH,
            "retrieved_at": metadata["retrieved_at"],
        },
        "operational_kpis": {"documents": source_documents},
    }
    return tables, provenance


def select_snapshot(dataset_id: str, table):
    """Select every eligible historical row without deriving or editing values."""
    metrics = (
        FINANCIAL_METRICS if dataset_id == "financial_facts" else OPERATIONAL_METRICS
    )
    selected = []
    for row in table.to_pylist():
        instant = (
            row["metric_id"] in INSTANT_METRICS
            if dataset_id == "financial_facts"
            else row["metric_id"] == "fintech_mau"
        )
        disclosure = (
            row["filed_at"] if dataset_id == "financial_facts" else row["filing_date"]
        )
        if (
            row["metric_id"] not in metrics
            or row["period_end"] > REFERENCE_DATE_VALUE
            or row["period_type"] != ("INSTANT" if instant else "QUARTER")
            or disclosure > date.fromisoformat(DISCLOSURE_CUTOFF)
        ):
            continue
        if not instant:
            end = row["period_end"]
            quarter_end_month = ((end.month - 1) // 3 + 1) * 3
            quarter_end_day = calendar.monthrange(end.year, quarter_end_month)[1]
            quarter_start = date(end.year, quarter_end_month - 2, 1)
            if (
                end.month != quarter_end_month
                or end.day != quarter_end_day
                or row["period_start"] != quarter_start
            ):
                continue
        selected.append(row)
    selected.sort(
        key=lambda r: (
            r["metric_id"],
            r["period_end"],
            r["period_start"] or date.min,
            r.get("definition_version", ""),
            r["accession_number"],
        )
    )
    result = pa.Table.from_pylist(selected, schema=table.schema.remove_metadata())
    validate_table(dataset_id, result)
    required = (
        ("net_revenues_financial_income",)
        if dataset_id == "financial_facts"
        else ("gmv", "tpv")
    )
    for metric in required:
        if sum(r["metric_id"] == metric for r in selected) < 2:
            raise ValueError(
                "Insufficient existing comparable history for the public demo."
            )
    if dataset_id == "financial_facts":
        comparisons = financial_yoy(result.to_pandas(), "net_revenues_financial_income")
    else:
        comparisons = operational_yoy(result.to_pandas(), "gmv")
        tpv_comparisons = operational_yoy(result.to_pandas(), "tpv")
        if not any(
            row.period_end.date() == REFERENCE_DATE_VALUE
            and row.period_type == "QUARTER"
            for row in tpv_comparisons.itertuples()
        ):
            raise ValueError(
                "Public TPV snapshot lacks an eligible latest YoY comparison."
            )
    if not any(
        row.period_end.date() == REFERENCE_DATE_VALUE and row.period_type == "QUARTER"
        for row in comparisons.itertuples()
    ):
        raise ValueError("Public trend lacks an eligible latest YoY comparison.")
    if dataset_id == "operational_kpis" and not any(
        r["metric_id"] == "fintech_mau" for r in selected
    ):
        raise ValueError("Public Fintech snapshot needs an existing MAU fact.")
    return result


def build_bundle(source_data: Path, *, output_root: Path = BUNDLE_ROOT) -> dict:
    source_data = source_data.resolve()
    output_root = output_root.absolute()
    if (
        output_root.name != "v1"
        or output_root.parent.name != "demo_data"
        or output_root.resolve() != output_root
        or output_root.is_relative_to(source_data)
        or "data" in output_root.parts
    ):
        raise ValueError(
            "Export must target a separate demo_data/v1 directory without links."
        )
    expected, provenance = reviewed_sources(source_data)
    snapshots = {}
    inputs = {}
    for dataset_id in ARTIFACTS:
        source = source_data / "silver" / "sec" / f"{dataset_id}.parquet"
        table = pq.ParquetFile(source).read()
        assert_source_rows(table, expected[dataset_id])
        snapshots[dataset_id] = select_snapshot(dataset_id, table)
        inputs[dataset_id] = sha256(source)
    allowed = {"manifest.json", *ARTIFACTS.values()}
    if output_root.exists() and any(
        p.relative_to(output_root).as_posix() not in allowed
        for p in output_root.rglob("*")
        if p.is_file()
    ):
        raise ValueError(
            "Refusing to export into a directory containing unapproved artifacts."
        )
    for relative in allowed:
        _contained_path(output_root, relative)
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "bundle_id": "v1",
        "source_code_revision": CODE_REVISION,
        "builder_source_sha256": sha256(Path(__file__)),
        "history_policy_version": HISTORY_POLICY_VERSION,
        "snapshot_reference_date": REFERENCE_DATE,
        "snapshot_cutoff": DISCLOSURE_CUTOFF,
        "generated_at": "2026-10-13T00:00:00Z",
        "build_date_policy": "Fixed G31 release date; not a live refresh timestamp.",
        "selection_rule": (
            "All eligible reviewed QUARTER facts and INSTANT snapshots for the "
            "existing metric allowlists, through 2026-06-30 and disclosed by "
            "2026-10-06; exact reported quarter starts; preserve units, "
            "definitions and lineage; no YTD/FY conversion, value changes or "
            "derived quarters."
        ),
        "source_organization": "MercadoLibre, Inc.; disseminated by SEC EDGAR",
        "attribution": (
            "Independent portfolio project. No SEC or MercadoLibre endorsement, "
            "sponsorship, affiliation or approval. No source logos are included."
        ),
        "source_review": "docs/methodology/public_source_review.md",
        "provenance_policy": (
            "Exact reviewed Company Facts input and E1-E7 SEC exhibits; all "
            "exported columns match existing normalization/canonicalization, "
            "including revision lineage."
        ),
        "market_policy": (
            "Market data is not part of this bundle. No price observations or "
            "price-derived Market Cap Gold."
        ),
        "excluded_datasets": list(MARKET_EXCLUSIONS),
        "intentionally_missing_datasets": list(OPTIONAL_OMISSIONS),
        "builder_versions": {"pyarrow": pa.__version__},
        "datasets": {},
    }
    for dataset_id, relative in ARTIFACTS.items():
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        table = snapshots[dataset_id]
        pq.write_table(
            table, target, compression="zstd", version="2.6", use_dictionary=True
        )
        rows = table.to_pylist()
        entry = {
            "path": relative,
            "sha256": sha256(target),
            "row_count": table.num_rows,
            "schema_name": "FINANCIAL_FACTS_SCHEMA"
            if dataset_id == "financial_facts"
            else "OPERATIONAL_SCHEMA",
            "schema_version": "1",
            "methodology_version": (
                "existing Silver schema 1; unchanged selection/definitions"
            ),
            "metric_ids": sorted({r["metric_id"] for r in rows}),
            "period_types": sorted({r["period_type"] for r in rows}),
            "min_period_end": min(r["period_end"] for r in rows).isoformat(),
            "max_period_end": max(r["period_end"] for r in rows).isoformat(),
            "accessions": sorted({r["accession_number"] for r in rows}),
            "first_accessions": sorted({r["first_accession_number"] for r in rows}),
            "source_family": rows[0]["source"],
            "source_organization": "MercadoLibre, Inc.",
            "input_silver_sha256": inputs[dataset_id],
            "provenance": provenance[dataset_id],
            "coverage_by_metric": coverage_by_metric(dataset_id, table),
        }
        if dataset_id == "operational_kpis":
            entry["definition_versions"] = sorted(
                {r["definition_version"] for r in rows}
            )
        manifest["datasets"][dataset_id] = entry
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_bundle(output_root)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-data",
        type=Path,
        required=True,
        help="Read-only reviewed source data directory",
    )
    arguments = parser.parse_args()
    result = build_bundle(arguments.source_data)
    for dataset_id, entry in result["datasets"].items():
        print(f"{dataset_id}: {entry['row_count']} rows; SHA256 {entry['sha256']}")
