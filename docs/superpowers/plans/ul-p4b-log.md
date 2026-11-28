# UNIT_LINKED P4b implementation log

Branch `ul/p4b-stochastic`. Edits stay in the working tree for orchestrator review.

## Task 1 — Scenario probabilities and reduction

- Files: `src/avk/esg/{supplied,library}.py`, `src/avk/runs/scenario_statistics.py`,
  `tests/esg/test_library.py`, `tests/runs/test_scenario_statistics.py`.
- `uv run --no-sync pytest tests/esg tests/runs/test_scenario_statistics.py -q`:
  62 passed in 45.42s. The weighted round-trip and three reduction tests failed
  before implementation.
- Weight is optional in scenario Parquet, invariant within each path, and its
  per-path values must add to one within 1e-12. The writer retains the original
  layout for equal weights. Percentiles use the weighted inverse CDF and CTE
  uses fractional probability at the tail boundary. Zero-weight paths are ignored.
- Pre-change 10,000-policy UNIT_LINKED valuation captured with seed 209 in
  `.tmp/p4b-baseline`. The baseline wrote aggregate and seriatim reporting CSVs.
  Cold compilation took 74.58s.
- Next: configure and write summary outputs.

## Task 2 — Summary configuration and output

- Files: `src/avk/runs/{config,check,valuation}.py`, `src/avk/outputs/writers.py`,
  `tests/runs/test_scenario_summary.py`.
- `uv run --no-sync pytest tests/runs/test_scenario_summary.py -q`:
  13 passed in 14.09s with Numba capped at four threads. The positive summary
  configuration and deterministic-run validation assertions went red first.
- TERM and UNIT_LINKED each used 1,025 policies and two unequal-weight
  paths. All aggregate columns and steps were checked, and summaries matched
  byte for byte at batch sizes 256 and 2,048 with one and four threads.
- Settings are required when enabled. A column-step with any positive-weight
  nonfinite result has empty statistics. Output rows follow the existing aggregate
  column order and then step order.
- Next: TVOG helper and a TERM present-value check.

## Task 3 — TVOG

- Files: `src/avk/runs/scenario_statistics.py`, `src/avk/api.py`,
  `tests/runs/test_tvog.py`.
- `uv run --no-sync pytest tests/runs/test_tvog.py -q`: 7 passed in 6.31s
  with Numba capped at four threads. All seven failed before the API existed.
- `avk.api.tvog` takes a PV per path in scenario ID order plus the deterministic
  reference PV. It checks the measure and positive-weight PVs. TERM step-zero
  `MCEV_pvfp_BE` was tested with an unequal-weight risk-neutral set and the
  default deterministic reference-forward path.
- P2b handoff: wire step-zero market-consistent `pvfp`, `bel`, and `vif`
  (planned labels `MCEV_pvfp_MC`, `MCEV_bel_MC`, and `MCEV_vif_MC`).
  For guarantee-cost TVOG, discount `maturity_guarantee_A`,
  `maturity_guarantee_R`, and `dpf_guarantee_cost` on each MC path before passing
  a guarantee PV to the helper. Use consistent shareholder versus outgo signs,
  matched assumptions, and reference-forward fund returns for the CE run.
- Next: dynamic lapse, including a 10,000-policy explicit-off rerun.

## Task 4 — Dynamic lapse

- Files: `src/avk/runs/{config,cases,valuation}.py`,
  `src/avk/products/unit_linked/decrements.py`, `tests/unit_linked/test_dynamic_lapse.py`.
- `uv run --no-sync pytest tests/unit_linked/test_dynamic_lapse.py tests/unit_linked/test_decrements.py -q`:
  28 passed in 180.94s including cold JIT work. Eight tests failed before implementation.
- The basis-specific switch and parameters flow through Valuation. Only ordinary
  active and reduced paid-up surrender probabilities are adjusted. Opening fund
  divided by opening premiums paid sets moneyness. The factor is one if disabled
  or if premiums paid are zero. No variant, factory, or P2b formula changes.
- `uv run --no-sync avk run .tmp/p4b-baseline/explicit-off.json` and a binary
  comparison passed for both 10,000-policy reporting files against the pre-change run.
  Baseline gate/project/wall times were 1.70s/66.16s/142.96s (cold, default threads).
  Explicit-off times were 1.02s/3.15s/5.50s (warm, four threads).
  The separate timings reflect different cache and thread settings.
  - Aggregate SHA-256: `5567bbc268c2e7ca336e1c076300cb8f65077d1929e50342cad142a888b71deb`
  - Seriatim SHA-256: `4b18aed3507b26189919337772f0086f8f2efc814fc540314b040a80192bc858`
- Next: worked tutorial and project checks.

## Task 5 — Tutorial and repository verification

- Files: `docs/{unit-linked-stochastic,how-tos,scenarios}.md`, `CHANGELOG.md`,
  `docs/reference/run-file.md` (generated).
- Extracted and ran all four tutorial code blocks in order using
  `uv run --no-sync python .tmp/p4b_tutorial.py`. The example passed in 15.07s
  with the warm cache and four Numba threads. Month-12 95th percentile and
  upper CTE matched. The deterministic active unit maturity PV was 379,075,063.52,
  and the risk-neutral mean less that PV was 2,146,137.98. Dynamic surrender
  varied across the eight paths. CSV console output avoids Windows cp1252
  rendering errors from boxed Polars tables.
- `uv run --no-sync pytest tests/regression/test_documentation.py -q`:
  2 passed in 4.01s after the tutorial was verified.
- Review found ordinary cumulative sums could miss inverse-CDF boundaries due to
  roundoff. Added equal- and unequal-weight regression cases and replaced ordinary
  prefixes with compensated float64 prefix sums. `uv run --no-sync pytest tests/runs -q`
  passed 25 tests in 16.01s after the two cases went red.
- `NUMBA_DISABLE_JIT=1` with
  `uv run --no-sync pytest tests/unit_linked/test_dynamic_lapse.py -k active_surrender_uses_opening_moneyness -q`:
  4 passed and 9 deselected in 4.35s.
- All 171 files under `tests/saved` match their HEAD Git blobs byte for byte.
  `git diff --exit-code -- tests/saved` and `git diff --check` passed.
- Next: orchestrator review and commit the working tree.

### Project checks

| Command | Result |
|---|---|
| `uv run --no-sync ruff check .` | Pass, no findings |
| `uv run --no-sync ruff format --check .` | Pass, 231 files |
| `uv run --no-sync mypy` | Pass, 136 source files |
| `uv run --no-sync lint-imports` | Pass, 14 contracts kept and 0 broken |
| `uv run --no-sync python scripts/generate_reference.py --check` | Pass, reference current |
| `uv run --no-sync python scripts/generate_ul_fund_slots.py --check` | Pass, generated source current |
| `uv run --no-sync python scripts/check_clean_install.py` | Pass, 70.68s. Isolated runtime wheel installed 13 packages and ran the 8-policy TERM check and valuation. |
| `uv build` | Pass, 4.84s. Sdist and wheel built. The cache-location warning was informational. The sdist contains the new statistics module and excludes scratch/cache directories. |
| `uv run --no-sync pytest` | Pass, 460 passed and 9 deselected in 4,758.24s (1h 19m 18s). Stopped the preliminary run after the percentile correction and ran the final tree in full. |
| `uv run --no-sync pytest -m slow` | Pass, 7 passed and 462 deselected in 5,314.56s (1h 28m 34s). Includes the five 100,000-policy product regressions, the batch/thread byte comparison and the 10,000-policy UNIT_LINKED regression. |

Both final pytest suites used Python 3.14.8, pytest 9.1.1 and Numba capped at
four threads. The slow byte comparison explicitly exercises one and four
threads. The suites overlapped during the run. All requested checks passed,
and the working tree is ready for review. The open TVOG integration points
for P2b are listed in Task 3.
