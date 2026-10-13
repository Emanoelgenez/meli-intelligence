"""Offline integration of financial/operational identity, Arrow and strategy lineage."""
from io import BytesIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from meli_intelligence.evidence.adapters import build_evidence_registry
from meli_intelligence.evidence.model import EVIDENCE_COLUMNS, normalize_evidence
from meli_intelligence.storage.evidence import _SCHEMA
from meli_intelligence.strategy.pestel import build_pestel, validate_pestel_lineage
from meli_intelligence.strategy.swot import build_swot, validate_swot_lineage


@pytest.mark.integration
def test_financial_operational_registry_schema_and_strategy_lineage_in_memory():
    financial = pd.DataFrame([
        dict(metric_id="gross_profit", period_start=start, period_end="2012-09-30",
             value=100., unit="USD", accession_number=accession, source="SEC fixture")
        for start, accession in (("2012-06-26", "fixture-a"), ("2012-07-01", "fixture-b"))
    ] + [dict(metric_id="net_revenues_financial_income_yoy_growth", period_end="2024-03-31",
              value=20., unit="percent", source="SEC fixture")])
    operational = pd.DataFrame([dict(
        evidence_id="operational-source-id", metric_id="fintech_mau_yoy_growth",
        evidence_type="OBSERVATION", business_domain="Fintech", reference_date="2024-03-31",
        value=10., unit="percent", claim="Reported fintech users grew.", claim_kind="yoy_growth",
        source="SEC fixture", accession_number="operational-filing")])
    registry = build_evidence_registry(financial=financial, operational=operational)
    assert len(registry) == 4 and registry.evidence_id.is_unique
    assert "operational-source-id" in set(registry.evidence_id)
    assert list(registry.columns) == EVIDENCE_COLUMNS
    table = pa.Table.from_pandas(registry, schema=_SCHEMA, preserve_index=False, safe=True)
    table.validate(full=True)
    buffer = BytesIO()
    pq.write_table(table, buffer)
    restored = normalize_evidence(pq.read_table(BytesIO(buffer.getvalue())).to_pandas())
    # Arrow preserves the schema; pandas may infer nullable string dtypes on read.
    assert restored.evidence_id.tolist() == registry.evidence_id.tolist()
    assert pa.Table.from_pandas(restored, schema=_SCHEMA, preserve_index=False).equals(table)
    pestel = build_pestel(restored)
    swot = build_swot(restored, pestel)
    assert len(pestel) == 1 and pestel.pestel_dimension.tolist() == ["SOCIAL"]
    assert len(swot) == 2 and set(swot.swot_category) == {"STRENGTH"}
    validate_pestel_lineage(pestel, restored)
    validate_swot_lineage(swot, restored, pestel)
