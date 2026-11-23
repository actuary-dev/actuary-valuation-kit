# Actuary Valuation Kit on Windows
Use native PowerShell, Git, Python 3.13 or 3.14, and uv 0.12.19 or newer.
Install these tools first using their normal installers or your package manager.
Native verification uses Windows 11, PowerShell 5.1 and installed Python 3.14.
The examples use file inputs; optional SQL/GPU functionality is not required.

## Keep working files outside OneDrive
Keep the clone, environment, caches, temporary files, policy books and results
outside OneDrive or any other synced folder. A suitable parent is
`$HOME/avk-work`. Copy finished reports into a synced folder after a run.

From a local copy of the project, start PowerShell at the project root.

```powershell
$env:PATH = "$HOME/.local/bin;$env:PATH"
$env:UV_PROJECT_ENVIRONMENT = "$HOME/avk-work/env"
$env:UV_CACHE_DIR = "$HOME/avk-work/uv-cache"
$env:AVK_CACHE_DIR = "$HOME/avk-work/kernel-cache"
$env:NUMBA_CACHE_DIR = "$env:AVK_CACHE_DIR/numba"
$env:PYTHONUTF8 = '1'
$env:UV_PYTHON_DOWNLOADS = 'never'
$env:TEMP = "$HOME/avk-work/tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
uv sync --locked --extra ui --extra sql --dev
```

This installs the locked package and development tools into the chosen environment.
The ui extra supplies Plotly for notebooks; the sql extra supports the full
development suite and is not needed for CSV/Parquet examples.
Python downloads are disabled here. If a supported Python is missing, install
one, or select an installed interpreter with `$env:UV_PYTHON = '3.13'`
(or `'3.14'`) and repeat the sync.
The default Numba CPU selection is used; no CPU-name override is required.

## Long file paths

Windows has a 260-character path limit, and the longest file path in this
repository is 138 characters from the project root. Keep the path to your
clone folder under about 120 characters. If you move the uv cache, use a
similarly short path.

If Git or uv reports "Filename too long", enable long paths in Git:

```powershell
git config --global core.longpaths true
```

Retry the command, or install the ready-built wheel from
[GitHub Releases](https://github.com/actuary-dev/actuary-valuation-kit/releases).

## Check and run the invented Term example
Continue in the same PowerShell session:

```powershell
uv run avk demo generate "$HOME/avk-work/demo-term" --product TERM --count 10000 --seed 209
uv run avk check "$HOME/avk-work/demo-term/valuation.json"
uv run avk run "$HOME/avk-work/demo-term/valuation.json"
```

The generator writes invented inputs for 10,000 policies. Results are under
`demo-term/output/valuation`, including aggregate/seriatim CSVs,
`run_record.json`, `run_status.json`, `main.log` and `error.log`.
An empty error log is expected after success. Preserve the record and logs with
the exported results; see [the audit guide](audit-trail.md) for failures.
Read step **1** for the reported valuation-date row, and
**cashflows_be_reserves_BE** for the held reserve amount. Read
[the output conventions](output-conventions.md) before interpreting ratios.

Quote paths containing spaces. In JSON use forward slashes such as
`C:/books/term.parquet`, or escape each backslash.
Parquet uses the same policy columns as CSV;
see [Parquet books](inputs/parquet-policies.md).
Leave enough free disk space for temporary prepared books and output files.

## Guard 2: tutorials and notebooks
From the package directory in the same session:

```powershell
uv run pytest -q tests/regression/test_tutorials.py
```

Expected: **9 passed** (including three deliberately wrong tutorial controls). The guard installs the tutorial extension into a
temporary local discovery folder, checks/compiles/runs each product, then
executes copies of the three notebooks headlessly. Source notebooks retain
no outputs. The first compilation can take longer than a warm run.

To read and run a tutorial yourself, follow
[build your own Term](tutorials/term.md), [return of premium](tutorials/return_of_premium.md)
and [the format hook](tutorials/table_format.md). Notebook files are under
[notebooks](../notebooks/README.md).

## Contributor checks (optional after the walkthrough)
These run from the same package directory:

```powershell
uv run pytest -q
uv run python scripts/generate_reference.py --check
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
```

A nonzero exit code or FAILED line means a check failed; keep the output for
review. The default suite covers all five public 10k products, errors and
Guard 2. Never edit a saved result or tolerance to hide a difference.
The README documents the slow 100k suite, ordinary-Python oracle and build.
