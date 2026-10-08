"""Vertical pipeline from SEC Bronze to financial Silver."""

from __future__ import annotations

import json
from pathlib import Path

from meli_intelligence.config.settings import BRONZE_DIR
from meli_intelligence.storage.silver import (
    DEFAULT_FINANCIAL_FACTS_PATH,
    write_financial_facts_parquet,
)
from meli_intelligence.transformations.sec_companyfacts import (
    normalize_company_facts,
)


MELI_CIK = "0001099590"

DEFAULT_COMPANY_FACTS_BRONZE_PATH = (
    BRONZE_DIR
    / "sec"
    / "companyfacts"
    / f"CIK{MELI_CIK}_companyfacts.json"
)


def build_sec_financial_facts_silver(
    *,
    bronze_path: Path = DEFAULT_COMPANY_FACTS_BRONZE_PATH,
    output_path: Path = DEFAULT_FINANCIAL_FACTS_PATH,
) -> tuple[Path, Path]:
    """Build typed financial Silver from SEC Company Facts."""
    bronze_path = Path(bronze_path)

    payload = json.loads(
        bronze_path.read_text(
            encoding="utf-8"
        )
    )

    rows = normalize_company_facts(
        payload
    )

    cik = str(payload["cik"]).zfill(10)
    entity_name = payload["entityName"]

    return write_financial_facts_parquet(
        rows,
        entity_cik=cik,
        entity_name=entity_name,
        output_path=output_path,
        source_bronze_path=bronze_path,
    )