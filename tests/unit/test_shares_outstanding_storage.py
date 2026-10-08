"""Offline tests for the authoritative SEC shares-outstanding Silver dataset."""
from __future__ import annotations

from datetime import date
import hashlib
import json

import pandas as pd
import pytest

from meli_intelligence.analytics.market_cap import ENTITY, SEC_CONCEPT, SEC_METRIC_ID, SEC_SOURCE
from meli_intelligence.storage.shares_outstanding import (
    SHARES_OUTSTANDING_KEY,
    merge_shares_outstanding,
    read_shares_outstanding,
    validate_shares_outstanding,
    write_shares_outstanding,
)
from meli_intelligence.transformations.sec_companyfacts import normalize_shares_outstanding


def _payload() -> dict:
    return {
        "cik": 1099590,
        "entityName": ENTITY,
        "facts": {"dei": {SEC_CONCEPT: {"units": {"shares": [
            {"end": "2026-08-05", "val": 50_696_802, "filed": "2026-08-06",
             "accn": "0001099590-26-000023", "form": "10-Q"},
        ]}}}},
    }


def _row() -> dict:
    return normalize_shares_outstanding(_payload())[0]


def test_normalizer_output_is_valid_silver_input_and_preserves_sec_provenance():
    rows = normalize_shares_outstanding(_payload())
    validate_shares_outstanding(rows)
    row = rows[0]
    assert row["source_metric_id"] == SEC_METRIC_ID
    assert row["reference_date"] == date(2026, 8, 5)
    assert row["filed_at"] == date(2026, 8, 6)
    assert row["accession_number"] == "0001099590-26-000023"
    assert row["source"] == SEC_SOURCE


def test_silver_parquet_roundtrip_is_deterministic_and_idempotent(tmp_path):
    path = tmp_path / "silver" / "company" / "shares_outstanding.parquet"
    parquet_path, metadata_path = write_shares_outstanding(normalize_shares_outstanding(_payload()), path=path)
    assert parquet_path.exists() and metadata_path.exists()
    first = read_shares_outstanding(path)
    parquet_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    generated_at = json.loads(metadata_path.read_text(encoding="utf-8"))["generated_at"]
    write_shares_outstanding(normalize_shares_outstanding(_payload()), path=path)
    second = read_shares_outstanding(path)
    pd.testing.assert_frame_equal(first, second)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == parquet_hash
    assert hashlib.sha256(metadata_path.read_bytes()).hexdigest() == metadata_hash
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["generated_at"] == generated_at
    assert len(second) == 1
    assert second.iloc[0].value == 50_696_802


def test_new_authoritative_fact_appends_without_rewriting_history(tmp_path):
    path = tmp_path / "silver" / "company" / "shares_outstanding.parquet"
    first_rows = normalize_shares_outstanding(_payload())
    write_shares_outstanding(first_rows, path=path)
    first_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    first_metadata = json.loads(path.with_suffix(path.suffix + ".metadata.json").read_text(encoding="utf-8"))

    payload = _payload()
    observations = payload["facts"]["dei"][SEC_CONCEPT]["units"]["shares"]
    observations.append({
        "end": "2026-09-30", "val": 50_690_000, "filed": "2026-10-01",
        "accn": "0001099590-26-000030", "form": "10-Q",
    })
    write_shares_outstanding(normalize_shares_outstanding(payload), path=path)

    output = read_shares_outstanding(path)
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    second_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert len(output) == 2
    assert set(output.accession_number) == {"0001099590-26-000023", "0001099590-26-000030"}
    assert hashlib.sha256(path.read_bytes()).hexdigest() != first_hash
    assert first_metadata["row_count"] == 1
    assert second_metadata["row_count"] == 2


def test_semantically_identical_duplicates_deduplicate_deterministically():
    row = _row()
    duplicate = {**row, "source_bronze_file": "bronze/z.json"}
    # Bronze lineage is optional and does not redefine the SEC fact key.
    result_a = merge_shares_outstanding(pd.DataFrame(), [row, duplicate])
    result_b = merge_shares_outstanding(pd.DataFrame(), [duplicate, row])
    pd.testing.assert_frame_equal(result_a, result_b)
    assert len(result_a) == 1
    assert tuple(result_a.iloc[0][list(SHARES_OUTSTANDING_KEY)]) == tuple(
        result_b.iloc[0][list(SHARES_OUTSTANDING_KEY)]
    )


def test_conflicting_duplicate_provenance_key_is_rejected():
    row = _row()
    conflict = {**row, "value": 50_000_000.0}
    with pytest.raises(ValueError, match="Conflicting shares-outstanding"):
        merge_shares_outstanding(pd.DataFrame(), [row, conflict])


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_non_positive_or_non_finite_shares_are_rejected(value):
    row = {**_row(), "value": value}
    with pytest.raises(ValueError, match="cannot be null|positive finite whole shares"):
        validate_shares_outstanding([row])


@pytest.mark.parametrize(
    ("field", "value"),
    [("taxonomy", "us-gaap"), ("concept", "WeightedAverageNumberOfSharesOutstandingBasic"),
     ("source_metric_id", "us-gaap:Shares"), ("unit", "USD")],
)
def test_non_authoritative_taxonomy_concept_or_unit_is_rejected(field, value):
    row = {**_row(), field: value}
    with pytest.raises(ValueError):
        validate_shares_outstanding([row])


def test_conflict_with_existing_silver_fails_without_replacing_authoritative_fact():
    original = _row()
    changed = {**original, "value": 50_000_000.0}
    existing = merge_shares_outstanding(pd.DataFrame(), [original])
    with pytest.raises(ValueError, match="Conflicting shares-outstanding"):
        merge_shares_outstanding(existing, [changed])
