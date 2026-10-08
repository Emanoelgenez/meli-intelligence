"""Offline public-mode isolation, legacy compatibility and all-page acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import os
import subprocess
import sys

import pandas as pd
import pytest
import pyarrow.parquet as pq

from meli_intelligence.ui import public_demo as demo
from meli_intelligence.ui.catalog import get_dataset_catalog, get_dataset_spec
from meli_intelligence.ui.data import dataset_exists, load_dataset
from meli_intelligence.ui.health import check_all_datasets, check_dataset_health
from meli_intelligence.ui.pages.data_quality_sources import source_preview

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def local_default(monkeypatch):
    monkeypatch.delenv("MELI_PUBLIC_DEMO", raising=False)


@pytest.fixture
def copied_bundle(tmp_path, monkeypatch):
    target = tmp_path / "demo_data" / "v1"
    shutil.copytree(demo.BUNDLE_ROOT, target)
    monkeypatch.setattr(demo, "BUNDLE_ROOT", target)
    return target


@pytest.mark.parametrize("value,expected", [
    (None, False), ("false", False), ("0", False), ("no", False), ("FALSE", False),
    ("true", True), ("1", True), ("yes", True), (" YES ", True),
])
def test_mode_parsing(monkeypatch, value, expected):
    if value is not None:
        monkeypatch.setenv("MELI_PUBLIC_DEMO", value)
    assert demo.public_demo_enabled() is expected


@pytest.mark.parametrize("value", ["", "on", "2", "maybe"])
def test_invalid_configuration_never_falls_back(monkeypatch, value):
    monkeypatch.setenv("MELI_PUBLIC_DEMO", value)
    with pytest.raises(ValueError, match="MELI_PUBLIC_DEMO"):
        get_dataset_catalog()


def test_local_paths_remain_exactly_storage_defaults(monkeypatch):
    from meli_intelligence.storage.silver import DEFAULT_FINANCIAL_FACTS_PATH
    from meli_intelligence.storage.operational_silver import DEFAULT_OPERATIONAL_SILVER_PATH
    from meli_intelligence.storage.market_prices import DEFAULT_MARKET_PRICES_PATH
    from meli_intelligence.storage.market_cap import DEFAULT_MARKET_CAP_PATH

    expected = dict(financial_facts=DEFAULT_FINANCIAL_FACTS_PATH,
                    operational_kpis=DEFAULT_OPERATIONAL_SILVER_PATH,
                    market_prices=DEFAULT_MARKET_PRICES_PATH, market_capitalization=DEFAULT_MARKET_CAP_PATH)
    absent_catalog = get_dataset_catalog()
    for value in ("0", "false", "no"):
        monkeypatch.setenv("MELI_PUBLIC_DEMO", value)
        assert get_dataset_catalog() == absent_catalog
        for dataset_id, path in expected.items():
            assert get_dataset_spec(dataset_id).default_path == path


@pytest.mark.parametrize("dataset_id", demo.MARKET_EXCLUSIONS + demo.OPTIONAL_OMISSIONS)
def test_excluded_datasets_never_inspected_even_with_overrides(monkeypatch, tmp_path, dataset_id):
    path = tmp_path / "data" / f"{dataset_id}.parquet"
    path.parent.mkdir()
    pd.DataFrame({"reference_date": [pd.Timestamp("2026-06-30")], "value": [999.]}).to_parquet(path)
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    monkeypatch.setattr(demo, "validate_bundle", lambda *a: pytest.fail("Excluded dataset inspected the bundle"))
    assert not dataset_exists(dataset_id, path=path)
    health = check_dataset_health(dataset_id, path=path)
    assert health.status == "MISSING" and "public demo" in health.message
    assert "data" not in Path(health.path).parts[-2:]
    for reader in (load_dataset, source_preview):
        with pytest.raises(demo.PublicDemoExcluded):
            reader(dataset_id, path=path)


def test_public_catalog_and_approved_path_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    catalog = get_dataset_catalog()
    assert len(catalog) == 14
    assert all(spec.default_path.is_relative_to(demo.BUNDLE_ROOT) for spec in catalog)
    assert {h.dataset_id for h in check_all_datasets() if h.status == "AVAILABLE"} == set(demo.ARTIFACTS)
    assert len(load_dataset("financial_facts")) == 30
    assert len(load_dataset("operational_kpis")) == 20
    for dataset_id, relative in demo.ARTIFACTS.items():
        assert not load_dataset(dataset_id, path=demo.BUNDLE_ROOT / relative).empty
        with pytest.raises(PermissionError):
            load_dataset(dataset_id, path=tmp_path / "data" / relative)
        assert check_dataset_health(dataset_id, path=tmp_path / relative).status == "INVALID"


def test_missing_core_never_falls_back_to_existing_local_file(copied_bundle, monkeypatch, tmp_path):
    local = tmp_path / "data" / "financial_facts.parquet"
    local.parent.mkdir()
    shutil.copyfile(copied_bundle / demo.ARTIFACTS["financial_facts"], local)
    (copied_bundle / demo.ARTIFACTS["financial_facts"]).unlink()
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    assert not dataset_exists("financial_facts")
    assert check_dataset_health("financial_facts").status == "MISSING"
    with pytest.raises(FileNotFoundError, match="no local fallback"):
        load_dataset("financial_facts")
    with pytest.raises(PermissionError):
        load_dataset("financial_facts", path=local)


@pytest.mark.parametrize("damage", ["hash", "path", "extra_dataset", "manifest", "extra_file", "schema"])
def test_corrupt_bundle_fails_closed(copied_bundle, monkeypatch, damage):
    manifest_path = copied_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if damage == "hash":
        manifest["datasets"]["financial_facts"]["sha256"] = "0" * 64
    elif damage == "path":
        manifest["datasets"]["financial_facts"]["path"] = "../../data/private.parquet"
    elif damage == "extra_dataset":
        manifest["datasets"]["market_prices"] = {}
    elif damage == "extra_file":
        (copied_bundle / "market_prices.parquet").write_bytes(b"restricted")
    elif damage == "schema":
        path = copied_bundle / demo.ARTIFACTS["financial_facts"]
        pd.DataFrame({"value": [1]}).to_parquet(path)
        manifest["datasets"]["financial_facts"]["sha256"] = demo.sha256(path)
    manifest_path.write_text("invalid json" if damage == "manifest" else json.dumps(manifest))
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    assert check_dataset_health("financial_facts").status == "INVALID"
    assert check_dataset_health("operational_kpis").status == "INVALID"
    with pytest.raises(ValueError):
        load_dataset("financial_facts")
    assert check_dataset_health("market_prices").status == "MISSING"


def test_link_escape_rejected_before_data_read(copied_bundle, monkeypatch, tmp_path):
    path = copied_bundle / demo.ARTIFACTS["financial_facts"]
    outside = tmp_path / "private.parquet"
    shutil.move(path, outside)
    try:
        path.symlink_to(outside)
    except OSError:
        # Windows unprivileged symlink creation may be unavailable; also test the
        # resolver's canonicalization boundary without relying on OS privileges.
        original = Path.resolve
        monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: outside if self == path else original(self, *a, **k))
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    with pytest.raises(ValueError, match="escape"):
        load_dataset("financial_facts")


def _production_market_files(tmp_path):
    """Create valid local Market fixtures outside repository data/."""
    from meli_intelligence.analytics.market_cap import build_market_cap_gold
    from meli_intelligence.storage.market_cap import write_market_cap_gold

    market = pd.DataFrame([{
        "ticker": "MELI", "entity": "MercadoLibre, Inc.", "reference_date": pd.Timestamp("2026-06-30").date(),
        "open": 100., "high": 100., "low": 100., "close": 100., "volume": 1000.,
        "currency": "USD", "exchange": "NASDAQ", "mic_code": "XNGS", "source": "Twelve Data",
        "source_url": "https://api.twelvedata.com/time_series?symbol=MELI",
        "retrieved_at": "2026-07-01T00:00:00Z", "source_bronze_file": "fixture.json",
        "source_content_sha256": "a" * 64,
    }])
    from meli_intelligence.transformations.sec_companyfacts import normalize_shares_outstanding
    shares = normalize_shares_outstanding({"cik": 1099590, "entityName": "MercadoLibre, Inc.",
        "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{
            "end": "2026-06-29", "val": 50000000, "filed": "2026-06-29",
            "accn": "0001099590-26-000017", "form": "10-Q",
        }]}}}}})
    gold = build_market_cap_gold(market, shares)
    prices = tmp_path / "data" / "silver" / "market" / "market_prices.parquet"
    prices.parent.mkdir(parents=True)
    market.to_parquet(prices, index=False)
    cap = tmp_path / "data" / "gold" / "market" / "market_capitalization.parquet"
    write_market_cap_gold(gold, path=cap)
    return prices, cap


def test_valid_production_market_is_usable_locally_but_denied_publicly(tmp_path, monkeypatch):
    from meli_intelligence.ui.valuation_storytelling import valuation_view

    prices, cap = _production_market_files(tmp_path)
    from meli_intelligence.storage import market_prices, market_cap
    monkeypatch.setattr(market_prices, "DEFAULT_MARKET_PRICES_PATH", prices)
    monkeypatch.setattr(market_cap, "DEFAULT_MARKET_CAP_PATH", cap)
    assert get_dataset_spec("market_prices").default_path == prices
    assert not load_dataset("market_prices").empty
    assert dataset_exists("market_prices", path=prices)
    assert check_dataset_health("market_capitalization", path=cap).status == "AVAILABLE"
    local_gold = load_dataset("market_capitalization", path=cap)
    local_price = load_dataset("market_prices", path=prices)
    before = valuation_view(local_gold, None)
    assert before is not None and before.market_cap.value == 5_000_000_000
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    for dataset_id, path in (("market_prices", prices), ("market_capitalization", cap)):
        assert check_dataset_health(dataset_id).status == "MISSING"
        with pytest.raises(demo.PublicDemoExcluded):
            load_dataset(dataset_id)
        assert not dataset_exists(dataset_id, path=path)
        assert check_dataset_health(dataset_id, path=path).status == "MISSING"
        with pytest.raises(demo.PublicDemoExcluded):
            load_dataset(dataset_id, path=path)
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "false")
    pd.testing.assert_frame_equal(load_dataset("market_prices", path=prices), local_price)
    assert valuation_view(load_dataset("market_capitalization", path=cap), None) == before
    # Mode transitions also cannot reuse a cached private frame.
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "true")
    with pytest.raises(demo.PublicDemoExcluded):
        load_dataset("market_prices", path=prices)


def test_local_company_readers_and_analytical_parity(monkeypatch, tmp_path):
    from meli_intelligence.ui.financial_storytelling import select_financial_snapshots, select_financial_trend
    from meli_intelligence.ui.domain_storytelling import select_domain_snapshots, select_domain_trend

    local_frames = {}
    for dataset_id, relative in demo.ARTIFACTS.items():
        path = tmp_path / "data" / Path(relative).name
        path.parent.mkdir(exist_ok=True)
        shutil.copyfile(demo.BUNDLE_ROOT / relative, path)
        local_frames[dataset_id] = load_dataset(dataset_id, path=path)
    monkeypatch.setenv("MELI_PUBLIC_DEMO", "1")
    public = {dataset_id: load_dataset(dataset_id) for dataset_id in demo.ARTIFACTS}
    for dataset_id in public:
        pd.testing.assert_frame_equal(public[dataset_id], local_frames[dataset_id])
    assert select_financial_snapshots(public["financial_facts"]) == select_financial_snapshots(local_frames["financial_facts"])
    assert len(select_financial_trend(public["financial_facts"])) >= 2
    for domain in ("Commerce", "Fintech"):
        assert select_domain_snapshots(public, domain) == select_domain_snapshots(local_frames, domain)
        assert len(select_domain_trend(public, domain)) >= 2


def test_public_clean_checkout_all_pages_without_keys_or_network():
    # AppTest imports Streamlit by design. Run it separately so legacy tests can
    # still prove importing the application's helpers does not import Streamlit.
    script = r'''
from pathlib import Path
import socket
import httpx
from streamlit.testing.v1 import AppTest
from meli_intelligence.ui.pages import NAVIGATION_OPTIONS
from meli_intelligence.sources.sec.client import SecClient
from meli_intelligence.sources.sec.operational_releases import OperationalReleaseClient

def forbidden(*args, **kwargs):
    raise AssertionError("Runtime HTTP or ingestion client")
httpx.Client.send = forbidden
httpx.AsyncClient.send = forbidden
SecClient.__init__ = forbidden
OperationalReleaseClient.__init__ = forbidden
connect = socket.socket.connect
def guarded_connect(sock, address):
    if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
        return connect(sock, address)  # Windows asyncio socketpair only.
    raise AssertionError("Outbound connection during public navigation")
socket.socket.connect = guarded_connect
root = Path.cwd()
assert sorted(p.relative_to(root / "data").as_posix() for p in (root / "data").rglob("*") if p.is_file()) == ["bronze/.gitkeep", "gold/.gitkeep", "silver/.gitkeep"]
app = AppTest.from_file(str(root / "streamlit_app.py"), default_timeout=30).run()
for page in NAVIGATION_OPTIONS:
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, page
    assert any("Portfolio demo mode" in item.value for item in app.info)
    if page in {"Executive Overview", "Financial", "Commerce", "Fintech"}:
        assert len(app.metric) >= 2, page
    if page == "Market":
        assert not app.metric
        assert any("intentionally excluded" in item.value for item in app.warning)
    if page in {"Macro", "Product Evidence", "PESTEL", "SWOT"}:
        messages = [x.value for x in (*app.info, *app.warning, *app.caption)]
        assert any("MISSING" in x or "unavailable" in x.lower() for x in messages), page
    if page == "Data Quality & Sources":
        frame = app.dataframe[0].value
        assert len(frame) == 14
        assert frame.status.str.startswith("Available").sum() == 2
print("All ten pages: PASS; no keys, no outbound HTTP, no production payloads")
'''
    environment = dict(os.environ, MELI_PUBLIC_DEMO="1", PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    environment.pop("SEC_USER_AGENT", None)
    environment.pop("TWELVE_DATA_API_KEY", None)
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "All ten pages: PASS" in result.stdout


def test_banner_absent_in_local_mode():
    class RecordingUI:
        def info(self, value):
            pytest.fail("Public banner in local mode")
    demo.render_public_demo_notice(RecordingUI())
