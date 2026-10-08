"""Tests for operational-release Bronze storage."""

from __future__ import annotations

import hashlib
import json

from meli_intelligence.sources.sec.operational_releases import (
    OperationalRelease,
)
from meli_intelligence.storage import (
    operational_bronze,
)


def test_save_operational_release_bronze(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        operational_bronze,
        "BRONZE_DIR",
        tmp_path,
    )

    release = OperationalRelease(
        cik="0001099590",
        accession_number=(
            "0001099590-26-000021"
        ),
        filing_date="2026-08-05",
        sec_report_date="2026-06-30",
        filing_index_url=(
            "https://example.com/index"
        ),
        exhibit_url=(
            "https://example.com/release.htm"
        ),
        document_name="release.htm",
    )

    content = (
        b"<html>raw release</html>"
    )

    html_path, metadata_path = (
        operational_bronze
        .save_operational_release_bronze(
            content,
            release,
        )
    )

    assert (
        html_path.read_bytes()
        == content
    )

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    assert metadata["reference_period"] is None

    assert (
        metadata["sec_report_date"]
        == "2026-06-30"
    )

    assert (
        metadata["accession_number"]
        == "0001099590-26-000021"
    )

    assert (
        metadata["content_sha256"]
        == hashlib.sha256(
            content
        ).hexdigest()
    )