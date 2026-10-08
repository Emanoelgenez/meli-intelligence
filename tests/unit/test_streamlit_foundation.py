from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from meli_intelligence.ui.catalog import get_dataset_catalog, get_dataset_spec, list_dataset_ids
from meli_intelligence.ui.data import dataset_exists, load_dataset
from meli_intelligence.ui.filters import BUSINESS_DOMAINS, FilterState, apply_filters
from meli_intelligence.ui.health import DatasetHealth, check_all_datasets, check_dataset_health, summarize_health
from meli_intelligence.ui.pages import NAVIGATION_OPTIONS
from meli_intelligence.ui.pages.executive_overview import availability_by_domain_layer


def _write_parquet(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def test_catalog_is_unique_ordered_and_uses_project_paths():
    catalog = get_dataset_catalog()
    ids = [spec.dataset_id for spec in catalog]
    assert len(ids) == len(set(ids))
    assert tuple(ids) == list_dataset_ids()
    assert ids == sorted(ids)
    assert all(spec.default_path for spec in catalog)
    assert all(spec.business_domain is None or spec.business_domain for spec in catalog)
    assert all(spec.query_capability for spec in catalog)
    assert all(spec.layer in {"Silver", "Gold"} for spec in catalog)
    assert all(set(spec.business_domains).issubset(BUSINESS_DOMAINS) for spec in catalog)
    assert all(spec.default_path.suffix.lower() == ".parquet" for spec in catalog)
    assert all(spec.default_path.is_absolute() for spec in catalog)


def test_sprint_5a_production_source_has_no_machine_specific_paths():
    project_root = Path(__file__).resolve().parents[2]
    source_files = [project_root / "streamlit_app.py"]
    source_files.extend((project_root / "src" / "meli_intelligence" / "ui").rglob("*.py"))
    machine_paths = ("c:\\projetos\\invest", "c:\\users\\truechange")

    for source_path in source_files:
        normalized_source = source_path.read_text(encoding="utf-8").replace("/", "\\").casefold()
        assert all(path not in normalized_source for path in machine_paths), str(source_path)


def test_catalog_unknown_id_fails():
    with pytest.raises(ValueError, match="Unknown dataset_id"):
        get_dataset_spec("not_a_dataset")


def test_health_missing_empty_available_invalid_and_latest_date(tmp_path):
    missing = check_dataset_health("macro_indicators", path=tmp_path / "missing.parquet")
    assert missing.status == "MISSING"
    empty_path = _write_parquet(pd.DataFrame({"reference_date": pd.Series(dtype="datetime64[ns]")}), tmp_path / "empty.parquet")
    empty = check_dataset_health("macro_indicators", path=empty_path)
    assert (empty.status, empty.row_count, empty.column_count) == ("EMPTY", 0, 1)
    available_path = _write_parquet(
        pd.DataFrame({"reference_date": [date(2024, 1, 31), date(2024, 2, 29)], "value": [1.0, 2.0]}),
        tmp_path / "available.parquet",
    )
    available = check_dataset_health("macro_indicators", path=available_path)
    assert (available.status, available.row_count, available.column_count) == ("AVAILABLE", 2, 2)
    assert available.latest_reference_date == date(2024, 2, 29)
    no_date = _write_parquet(pd.DataFrame({"value": [1]}), tmp_path / "no-date.parquet")
    assert check_dataset_health("macro_indicators", path=no_date).latest_reference_date is None
    invalid_path = tmp_path / "invalid.parquet"
    invalid_path.write_bytes(b"not a parquet")
    assert check_dataset_health("macro_indicators", path=invalid_path).status == "INVALID"


def test_all_health_checks_preserve_catalog_order(monkeypatch):
    from meli_intelligence.ui import health

    monkeypatch.setattr(health, "_check", lambda spec, path: DatasetHealth(spec.dataset_id, "MISSING", str(path), None, None, None, "missing"))
    assert tuple(item.dataset_id for item in check_all_datasets()) == list_dataset_ids()


def test_data_access_missing_and_valid_parquet(tmp_path):
    assert not dataset_exists("macro_indicators", path=tmp_path / "missing.parquet")
    with pytest.raises(FileNotFoundError):
        load_dataset("macro_indicators", path=tmp_path / "missing.parquet")
    path = _write_parquet(pd.DataFrame({"metric_id": ["m1"], "reference_date": [date(2024, 1, 31)], "value": [1.]}), tmp_path / "macro.parquet")
    frame = load_dataset("macro_indicators", path=path)
    assert frame.loc[0, "metric_id"] == "m1"


def test_filters_dates_domains_copy_and_non_applicable_behavior():
    frame = pd.DataFrame({
        "business_domain": ["Macro", "Commerce"],
        "reference_date": [date(2024, 1, 31), date(2024, 2, 29)],
        "value": [1, 2],
    })
    filtered = apply_filters(frame, FilterState("Commerce", date(2024, 2, 1), date(2024, 2, 29)))
    assert len(filtered) == 1 and filtered.iloc[0].value == 2
    assert len(frame) == 2
    unsupported = pd.DataFrame({"value": [1, 2]})
    assert apply_filters(unsupported, FilterState("Macro", date(2024, 1, 1), None)).equals(unsupported)
    with pytest.raises(ValueError, match="on or before"):
        FilterState(start_date=date(2024, 2, 1), end_date=date(2024, 1, 1)).validate()
    with pytest.raises(ValueError, match="Unsupported business_domain"):
        FilterState(business_domain="Unknown").validate()


def test_health_summary_and_navigation_are_deterministic():
    health = [
        DatasetHealth("financial_facts", "AVAILABLE", "a", 2, 1, date(2024, 1, 31), "ok"),
        DatasetHealth("b", "MISSING", "b", None, None, None, "missing"),
        DatasetHealth("c", "EMPTY", "c", 0, 1, None, "empty"),
        DatasetHealth("d", "INVALID", "d", None, None, None, "invalid"),
    ]
    summary = summarize_health(health)
    assert summary == {
        "available_count": 1, "missing_count": 1, "empty_count": 1,
        "invalid_count": 1, "latest_reference_date": date(2024, 1, 31), "dataset_count": 4,
    }
    assert NAVIGATION_OPTIONS == (
        "Executive Overview", "Financial", "Commerce", "Fintech", "Macro", "PESTEL", "SWOT",
        "Product Evidence", "Market", "Data Quality & Sources",
    )
    assert not availability_by_domain_layer(health[:1], get_dataset_catalog()).empty


def test_page_layer_has_no_ingestion_or_analytics_logic():
    root = Path(__file__).resolve().parents[2] / "src" / "meli_intelligence" / "ui" / "pages"
    for path in root.glob("*.py"):
        content = path.read_text(encoding="utf-8").casefold()
        assert "meli_intelligence.sources" not in content
        assert "meli_intelligence.pipelines" not in content
        assert "calculate_yoy" not in content and "calculate_cagr" not in content
        assert "write_parquet" not in content and "write_" not in content


def test_ui_helper_import_does_not_require_streamlit():
    import meli_intelligence.ui.catalog  # noqa: F401
    import meli_intelligence.ui.data  # noqa: F401
    import meli_intelligence.ui.health  # noqa: F401
    import meli_intelligence.ui.filters  # noqa: F401


@pytest.mark.parametrize("explicit", [False, True])
def test_entrypoint_bootstraps_root_before_first_package_import(tmp_path, explicit):
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    expected = tmp_path / "configured-root" if explicit else root
    expected.mkdir(exist_ok=True)
    environment = dict(os.environ, PYTHONPATH=str(root / "src"))
    environment.pop("MELI_PROJECT_ROOT", None)
    environment.pop("MELI_PUBLIC_DEMO_ROOT", None)
    if explicit:
        environment["MELI_PROJECT_ROOT"] = str(expected)
    script = r'''
import builtins
import os
from pathlib import Path
import runpy
import sys

entrypoint, expected = map(Path, sys.argv[1:])
assert Path.cwd() != entrypoint.parent
assert not any(name.startswith("meli_intelligence") for name in sys.modules)
original_import = builtins.__import__
seen = []

def guarded_import(name, *args, **kwargs):
    if name == "meli_intelligence" or name.startswith("meli_intelligence."):
        assert os.environ.get("MELI_PROJECT_ROOT") == str(expected)
        seen.append(name)
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
runpy.run_path(str(entrypoint), run_name="entrypoint_contract")
assert seen
from meli_intelligence.config.settings import PROJECT_ROOT
from meli_intelligence.ui.public_demo import BUNDLE_ROOT
assert PROJECT_ROOT == expected.resolve()
assert BUNDLE_ROOT == expected.resolve() / "demo_data" / "v1"
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(root / "streamlit_app.py"), str(expected)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
