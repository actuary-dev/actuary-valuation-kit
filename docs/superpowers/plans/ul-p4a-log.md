
# P4a scenario tooling handoff

Branch: `ul/p4a-scenarios`. All edits stay in the working tree for the
orchestrator. The supplied worktree and this log supersede the plan's commit
steps and the execution skill's commit-based bookkeeping.

## Task 1 — Settings and validation

- Files: `src/avk/esg/multi_asset.py`, `tests/esg/test_multi_asset_settings.py`.
- Tests: `uv run pytest tests/esg -q` — 24 passed after the initial missing-module failures.
- Ruling: `Risk_Free` must be outside `Assets` to keep the discount path deterministic.
  A variable intended to serve both roles needs a separate declared risk-free series.
- Ruling: require exact correlation labels and reorder the matrix to Assets CSV order.
  Hash the same file bytes used to parse the settings so the provenance is reproducible.
- Next: Task 2, seeded path generation and numerical tests.


## Task 2 — Generator

- Files: `src/avk/esg/multi_asset.py`, `src/avk/esg/deterministic.py`,
  `tests/esg/test_multi_asset.py`.
- Tests: `uv run pytest tests/esg -q` — 33 passed (9 failed before implementation).
  The monthly moment, correlation, and martingale checks each used 20,000 paths.
- Ruling: use the declared placement rule on a unit series to identify structural
  zeros. An actual 0% curve rate remains eligible for stochastic returns. The
  deterministic generator's existing calculation and result are unchanged.
- Ruling: simulate with PCG64 seeded by the child SeedSequence. Record a uint64
  token derived from the child as the Parquet-compatible Seed. Paired paths
  share that token and use opposing shocks. Zero volatility gives the drift
  exactly, including the risk-free drift under the risk-neutral measure.
- Next: Task 3, generator selection and TERM valuation parity.


## Task 3 — Registry with settings

- Files: `src/avk/esg/registry.py`, `src/avk/esg/deterministic.py`,
  `src/avk/esg/multi_asset.py`, `tests/esg/test_registry.py`.
- Tests: `uv run pytest tests/esg -q` — 38 passed (3 registry failures before wiring).
  Four TERM paths project and all four zero-volatility paths match the deterministic
  valuation under AVK's existing generated-output parity classes.
- Ruling: the only existing run-layer registry call already passes the run-file folder.
  It needed no edit for this task. Report both settings CSVs in the run input audit.
- `uv run pytest tests/regression/test_demo_suite.py -q` — 42 passed, 6 slow tests deselected.
- Next: Task 4, scenario file export and deterministic library.


## Task 4 — Scenario files and deterministic library

- Files: `src/avk/esg/library.py`, `src/avk/cli.py`, `src/avk/runs/check.py`,
  `src/avk/runs/scenarios.py`, `tests/esg/test_library.py`,
  `tests/esg/test_scenarios_cli.py`.
- Tests: `uv run pytest tests/esg -q` — 53 passed (15 new tests failed
  before the library module and CLI were implemented). TERM re-read the
  generated arrays, numeric IDs and uint64 seeds exactly, then ran Valuation.
- Ruling: scenario CLI commands load only the selected product's curve bindings
  and share the valuation's fiscal timing and curve validation. The library
  always starts from the default deterministic path. Pass its timing masks
  explicitly to flat/shift so genuine 0% rates can change and the deterministic
  generator's existing output does not need extra metadata.
- Ruling: serialize the in-memory deterministic ID as scenario 1 and the absent
  seed as 0, per the integer-only format. Preserve canonical numeric IDs and
  seeds exactly, and reject weights or IDs the supplied format cannot round-trip.
  Validate all library entries before publishing and replace each Parquet file atomically.
- Ruling: custom CSV paths are relative to the library JSON. Shock factors are
  positive and monthly effective rates exceed -1. Names are safe unique file stems.
- Next: Task 5, documentation and full project checks.


## Task 5 — Documentation and checks

- Files: `docs/scenarios.md`, `docs/how-tos.md`, `CHANGELOG.md`,
  `src/avk/esg/supplied.py`. Added final type annotations in `registry.py` and
  `library.py`. Reference regeneration produced no content changes.
- Tests: `uv run pytest tests/regression/test_documentation.py -q` — 2 passed.
- `uv run python scripts/generate_reference.py --check` passed.
- Ruling: repository-wide Ruff format check initially failed on two pre-existing
  examples in `docs/superpowers/plans/2026-11-26-ul-p1-inputs.md`. Apply the
  formatter to those examples so the unchanged check can pass.
- Next: orchestrator review and commit the working tree.


### Repository check results

| Command | Result |
|---|---|
| `uv run ruff check .` | Pass, no findings |
| `uv run ruff format --check .` | Pass, 184 files formatted after the P1 examples were formatted |
| `uv run mypy` | Pass, 118 source files |
| `uv run lint-imports` | Pass, 14 contracts kept and 0 broken |
| `uv run pytest` | Pass, 220 passed and 8 deselected in 43m 27s |
| `uv run python scripts/generate_reference.py --check` | Pass, reference current |
| `uv run python scripts/check_clean_install.py` | Pass, runtime-only wheel installed 13 packages. TERM input check and 8-policy valuation passed (2 reporting CSVs). |
| `uv build` | Pass, built 1 sdist and 1 wheel. The local cache warning was informational. The sdist contains the new modules and no `.uvcache` entries. |
| `uv run pytest -m slow` | Pass, 6 passed and 222 deselected in 57m 29s. Includes the 100k batch/thread byte comparison. |

`git diff --exit-code -- tests/saved` and `git diff --check` passed. Git reports no changes to the 171 tracked files under `tests/saved`. Raw Git object hashes matched all 170 saved Parquet files byte for byte.
Final review was performed inline as requested by the plan. All five review points were checked against the tests and diff.


Verification used the clone's Python 3.14.8 environment and pytest 9.1.1.
All five tasks and all repository checks are complete. Integration with the
UNIT_LINKED product remains in its own phases. The working tree is ready for
orchestrator review and commit.
