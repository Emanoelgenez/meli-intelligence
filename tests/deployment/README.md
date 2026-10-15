# Installed public-update regression

Run on Python 3.12 in a disposable environment with Git access to
`0edc3da65f34eb5b1a958e18e9ed5912ae8944f9` (the functional baseline):

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -c tests/deployment/cloud-constraints.txt uv
uv pip install -c tests/deployment/cloud-constraints.txt -e '.[dev]' wheel setuptools
python -m pytest tests/deployment -m integration -q -s
python -m pytest tests/unit -o pythonpath= -q
```

The test creates disposable virtual environments and installs the actual package
using both uv and pip. `--no-deps --no-build-isolation` reuse the prepared test
dependencies; installation of the application is real, not mocked. Child probes
use Python `-I` and remove PYTHONPATH; they do not inherit pytest's src injection.
The test copies only the public source/bundle/packaging files, never private data
or environment files.

The `normal` cases are negative controls: install the original with `.`, update
the checkout without reinstalling, and assert both datasets become INVALID.
The `editable` cases verify `-e .`; the `candidate` cases read the repository's
actual requirements.txt and therefore fail when it is reverted to `.`.

Successful updated installs must load 511/55 rows, preserve the revenue gap in
2025Q4, expose 33/11/11/11 observations and three YoY comparisons at 2026Q2, render
KPIs and charts on all four main pages, and reject an incompatible contract.
The uv normal/candidate cases also keep a real Streamlit WebSocket session open
through the source update. Polling watcher + runOnSave exercise module reloads
without restarting the server; a diagnostic test page uses the actual bundle
validator. The dashboard itself is exercised with AppTest in the installed
interpreter. This does not simulate Streamlit Cloud's private deployment service.

Known incident versions are constrained for tests, not imposed on deployment.
Record Python's patch version, uv, setuptools and the remaining resolved packages
alongside results. Editable installation tracks Python source edits; dependency,
package layout and build metadata changes still require reinstalling. A change
to dependency declarations must also deliberately trigger Cloud dependency
processing. Do not disable bundle validation to accommodate stale installations.

The `migration` cases additionally install the original normally, change the
requirements to the actual candidate and process dependencies in the same venv.
They require the original 30/20 bundle and all four pages to remain available
before updating source/data without another install. The persistent uv session
also asserts the resolved module path before and after that update.
