# Install on Linux
Use a local unsynced folder, Python 3.13 or 3.14, Git and uv 0.12.19 or newer.
Install those tools with your normal system/package manager first.
From a local copy of the project, start at the project root.

```sh
mkdir -p "$HOME/avk-work"
export UV_PROJECT_ENVIRONMENT="$HOME/avk-work/env"
export UV_CACHE_DIR="$HOME/avk-work/uv-cache"
export AVK_CACHE_DIR="$HOME/avk-work/kernel-cache"
export NUMBA_CACHE_DIR="$AVK_CACHE_DIR/numba"
export TMPDIR="$HOME/avk-work/tmp"
mkdir -p "$TMPDIR"
uv sync --locked --extra ui --extra sql --dev
uv run avk demo generate "$HOME/avk-work/demo-term" --product TERM --count 10000 --seed 209
uv run avk check "$HOME/avk-work/demo-term/valuation.json"
uv run avk run "$HOME/avk-work/demo-term/valuation.json"
uv run pytest -q tests/regression/test_tutorials.py
```

The locked install includes development tools and Plotly for the notebooks.
The sql extra is included for the complete development suite, not needed for file runs.
uv can install a supported Python if missing; to forbid downloads set
`UV_PYTHON_DOWNLOADS=never` and select an installed interpreter with `UV_PYTHON`.
Results are under `demo-term/output/valuation`. Keep logs and `run_record.json`
with results. See [conventions](output-conventions.md) and [how-tos](how-tos.md).
