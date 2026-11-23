# Actuary Valuation Kit
Actuary Valuation Kit is a regime-neutral life-insurance valuation engine. Python products built
from formula components compile into Numba kernels. It values Term, accidental-death,
critical-illness, disability and credit-life books, with cases, stress capital and
IFRS 17 GMM measurement and roll-forward. The public demo basis and books are invented.

Requires Python 3.13 or 3.14, Git and uv 0.12.19 or newer. Keep the clone,
environment, caches, books and results outside synced folders.
Follow [Windows installation](docs/WINDOWS.md) or [Linux installation](docs/LINUX.md).

## A 30-second example
After installation, start in the project root:

```sh
uv run avk demo generate /tmp/demo-term --product TERM --count 10000 --seed 209
uv run avk check /tmp/demo-term/valuation.json
uv run avk run /tmp/demo-term/valuation.json
```

PowerShell uses a writable path outside OneDrive:

```powershell
uv run avk demo generate "$HOME/avk-work/demo-term" --product TERM --count 10000 --seed 209
uv run avk check "$HOME/avk-work/demo-term/valuation.json"
uv run avk run "$HOME/avk-work/demo-term/valuation.json"
```

Results are in `demo-term/output/valuation`: aggregate and seriatim CSVs, logs,
status and an input-fingerprinted run record. Read step **1** for the reported date.
The held reserve is `cashflows_be_reserves_BE`; `*_pp` aggregates are book ratios.

## Scale
A seeded **100,000-policy Term** book over **372 months** took **3.6 to 4.2 seconds
warm wall time** on a reference laptop running on idle mains power: Windows 11,
Intel Core i7-13620H (10 cores / 16 logical processors), WSL Ubuntu 26.04,
**16 Numba threads**, batch size 8192. The committed baseline is 3.715 s.
This is a measured reference workload, not a promise for every machine or cold run.
No timing measurement is required for installation.

## Learn and use
- [Concepts](docs/concepts.md): components, bases, runs and measures.
- [How-tos](docs/how-tos.md): cases, capital, IFRS 17 and Python API.
- [Output conventions](docs/output-conventions.md): signs, ratios and timing.
- [Build your own Term](docs/tutorials/term.md), [add a premium refund](docs/tutorials/return_of_premium.md),
  [add a table format](docs/tutorials/table_format.md).
- [Three Plotly notebooks](notebooks/README.md).
- [Run-file keys](docs/reference/run-file.md), [input locations](docs/reference/inputs.md),
  [table formats](docs/reference/table-formats.md), [output columns](docs/reference/output-columns.md).
- [Developer reference](docs/developer/README.md), [audit trail](docs/audit-trail.md),
  [demo basis](src/avk/demo/README.md).

## Local checks
From the package directory, on Linux or PowerShell:

```sh
uv run pytest
uv run pytest -q tests/regression/test_tutorials.py
uv run python scripts/generate_reference.py --check
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv build
```

The default suite runs all five seeded 10k product books, clear-error guards and
headless tutorials/notebooks. `uv run pytest -m slow` runs 100k regressions and
batch/thread equality checks. Changes to saved reporting tables require review.
The optional `perf` group is for the idle reference laptop on mains only.
`NUMBA_DISABLE_JIT=1 uv run pytest -m purepython` runs the independent ordinary-Python
oracle on Linux. In PowerShell, set `$env:NUMBA_DISABLE_JIT = '1'`, run
`uv run pytest -m purepython`, then `Remove-Item Env:NUMBA_DISABLE_JIT`.

The optional `ui` extra supplies Plotly for the notebooks; `sql`, `mssql` and
`gpu` extras are not required for these examples. UI, GPU, SQL, stochastic runs
and a docs website remain outside the current release scope.
