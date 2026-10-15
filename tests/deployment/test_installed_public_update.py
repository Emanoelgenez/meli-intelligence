"""Real installed-package update regression; run with pytest -m integration.

Requires git objects for the last functional release and an interpreter with the
project dependencies, setuptools, wheel, pip and uv. No PYTHONPATH shortcut.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "0edc3da65f34eb5b1a958e18e9ed5912ae8944f9"
PUBLIC_PATHS = (
    "src",
    "demo_data",
    "streamlit_app.py",
    "pyproject.toml",
    "README.md",
    "requirements.txt",
)
PROBE = r"""
import json
from pathlib import Path
from meli_intelligence.ui import public_demo as demo
from meli_intelligence.ui.health import check_dataset_health
result = {
    "module": str(Path(demo.__file__).resolve()),
    "contract": getattr(demo, "CONTRACT_VERSION", "1"),
    "health": {d: check_dataset_health(d).status for d in demo.ARTIFACTS},
}
try:
    manifest = demo.validate_bundle()
    result["rows"] = {k: v["row_count"] for k,v in manifest["datasets"].items()}
except ValueError as exc:
    result["error"] = str(exc)
print(json.dumps(result))
"""
ACCEPTANCE = r"""
import json
from datetime import date
from pathlib import Path
from streamlit.testing.v1 import AppTest
from meli_intelligence.ui import public_demo as demo
from meli_intelligence.ui.data import load_dataset
from meli_intelligence.ui.financial_storytelling import (
    select_financial_trend, select_financial_yoy,
)
from meli_intelligence.ui.domain_storytelling import (
    select_domain_trend, select_domain_yoy,
)
assert Path(demo.__file__).resolve().is_relative_to(Path.cwd() / "src")
manifest = demo.validate_bundle()
frames = {d: load_dataset(d) for d in demo.ARTIFACTS}
assert {d: len(f) for d,f in frames.items()} == {
    "financial_facts": 511, "operational_kpis": 55,
}
assert len(select_financial_trend(frames["financial_facts"])) == 33
revenue = manifest["datasets"]["financial_facts"]["coverage_by_metric"][
    "net_revenues_financial_income"
]
assert "2025Q4" in revenue["missing_quarters"]
assert manifest["datasets"]["operational_kpis"]["coverage_by_metric"][
    "fintech_mau"
]["distinct_period_count"] == 11
comparisons = {"Revenue": select_financial_yoy(frames["financial_facts"])}
for domain in ("Commerce", "Fintech"):
    assert len(select_domain_trend(frames, domain)) == 11
    comparisons[domain] = select_domain_yoy(frames, domain)
assert all(c is not None and c[0] == date(2026, 6, 30) for c in comparisons.values())
# A corrupted contract must still fail closed after the installation correction.
manifest_path = demo.BUNDLE_ROOT / "manifest.json"
original = manifest_path.read_bytes()
try:
    corrupt = json.loads(original)
    corrupt["contract_version"] = "incompatible"
    manifest_path.write_text(json.dumps(corrupt))
    try:
        demo.validate_bundle()
    except ValueError as exc:
        assert "release contract" in str(exc)
    else:
        raise AssertionError("Incompatible contract was accepted")
finally:
    manifest_path.write_bytes(original)
app = AppTest.from_file(str(Path.cwd() / "streamlit_app.py"), default_timeout=90)
pages = {}
app.run()
for page in ("Visão geral", "Financeiro", "Comércio", "Serviços financeiros"):
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, page
    assert len(app.metric) >= 2, page
    charts = len(app.get("vega_lite_chart")) + len(app.get("arrow_vega_lite_chart"))
    assert charts >= 1, page
    pages[page] = {"metrics": len(app.metric), "charts": charts}
print(json.dumps({"pages": pages, "yoy": comparisons}, default=str))
"""


def _run(args, *, cwd, env):
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.integration
@pytest.mark.parametrize("installer", ["uv", "pip"])
@pytest.mark.parametrize("mode", ["normal", "editable", "candidate", "migration"])
def test_installed_package_tracks_checkout_update(tmp_path, installer, mode):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    archive = subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "archive", BASELINE, *PUBLIC_PATHS],
        cwd=ROOT,
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(checkout, filter="data")
    # Only public artifacts: the test never copies data/ or the developer .env.
    assert not (checkout / "data").exists()
    assert not (checkout / ".env").exists()
    requirement = {
        "normal": ".\n",
        "migration": ".\n",
        "editable": "-e .\n",
        "candidate": (ROOT / "requirements.txt").read_text(),
    }[mode]
    (checkout / "requirements.txt").write_text(requirement)
    environment = tmp_path / "installed"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Share only the prepared dependency directory, not the parent's source
    # paths or editable .pth files. Nested venvs do not inherit a parent venv.
    purelib = subprocess.check_output(
        [
            str(python),
            "-I",
            "-c",
            "import sysconfig; print(sysconfig.get_path('purelib'))",
        ],
        text=True,
    ).strip()
    (Path(purelib) / "g36_test_dependencies.pth").write_text(
        "\n".join(p for p in sys.path if Path(p).name == "site-packages") + "\n"
    )
    env = dict(os.environ)
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "MELI_PUBLIC_DEMO_ROOT",
        "SEC_USER_AGENT",
        "TWELVE_DATA_API_KEY",
    ):
        env.pop(key, None)
    env.update(
        MELI_PUBLIC_DEMO="1",
        MELI_PROJECT_ROOT=str(checkout),
        PYTHONDONTWRITEBYTECODE="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    if installer == "uv":
        install = [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
        ]
    else:
        install = [str(python), "-m", "pip", "install"]
    _run(
        [*install, "--no-deps", "--no-build-isolation", "-r", "requirements.txt"],
        cwd=checkout,
        env=env,
    )

    def probe():
        # -I also prevents accidental imports from the parent pytest process/cwd.
        return json.loads(_run([str(python), "-I", "-c", PROBE], cwd=checkout, env=env))

    before = probe()
    assert before["rows"] == {"financial_facts": 30, "operational_kpis": 20}
    assert before["health"] == dict.fromkeys(before["health"], "AVAILABLE")
    if mode == "migration":
        assert not Path(before["module"]).is_relative_to(checkout / "src")
        (checkout / "requirements.txt").write_text(
            (ROOT / "requirements.txt").read_text(encoding="utf-8"), encoding="utf-8"
        )
        _run(
            [*install, "--no-deps", "--no-build-isolation", "-r", "requirements.txt"],
            cwd=checkout,
            env=env,
        )
        stage_a = probe()
        assert stage_a["rows"] == before["rows"]
        assert Path(stage_a["module"]).is_relative_to(checkout / "src")
        print(json.dumps({"installer": installer, "stage_a_migration": stage_a}))
        baseline_pages = (
            "import json\nfrom pathlib import Path\n"
            "from streamlit.testing.v1 import AppTest\n"
            + ACCEPTANCE[ACCEPTANCE.index("app = AppTest") :].replace(
                '"yoy": comparisons', '"bundle": "original 30/20"'
            )
        )
        print(_run([str(python), "-I", "-c", baseline_pages], cwd=checkout, env=env))
    live = None
    if installer == "uv" and mode != "editable":
        from live_contract_session import LiveContractSession

        live = LiveContractSession(python, checkout, env)
        try:
            initial = live.read("1", expected_rows=before["rows"])
            assert Path(initial["module"]).is_relative_to(checkout / "src") == (
                mode != "normal"
            )
        except BaseException:
            live.close()
            raise
    try:
        # Simulate Git updating source + data in place. No package installation here.
        for relative in PUBLIC_PATHS:
            if relative == "requirements.txt":
                continue
            source, target = ROOT / relative, checkout / relative
            if source.is_dir():
                shutil.copytree(
                    source,
                    target,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
                )
            else:
                shutil.copyfile(source, target)
        after = probe()
        if live is not None:
            if mode == "normal":
                rendered = live.read("1", expected_error=after["error"])
            else:
                rendered = live.read(
                    "2", expected_rows={"financial_facts": 511, "operational_kpis": 55}
                )
            assert Path(rendered["module"]).is_relative_to(checkout / "src") == (
                mode != "normal"
            )
            print(json.dumps({"live_session": rendered, "same_pid": live.process.pid}))
    finally:
        if live is not None:
            live.close()
    print(
        json.dumps(
            {"installer": installer, "mode": mode, "before": before, "after": after}
        )
    )
    if mode == "normal":
        assert not Path(after["module"]).is_relative_to(checkout / "src")
        assert after["contract"] == "1"
        assert after["health"] == dict.fromkeys(after["health"], "INVALID")
        assert (
            after["error"]
            == "Public manifest does not match the approved release contract."
        )
    else:
        assert Path(after["module"]).is_relative_to(checkout / "src")
        assert after["contract"] == "2"
        assert after["rows"] == {"financial_facts": 511, "operational_kpis": 55}
        assert after["health"] == dict.fromkeys(after["health"], "AVAILABLE")
        print(_run([str(python), "-I", "-c", ACCEPTANCE], cwd=checkout, env=env))
