# UL P4b stochastic results — implementation plan

> Implement this plan inline, task by task, test first. Track each green task
> in `ul-p4b-log.md`. The orchestrator commits the working tree.

**Goal:** Weighted summaries of valuation aggregates, a generic TVOG calculation,
optional path-dependent UNIT_LINKED surrender, and a reproducible tutorial.

**Architecture:** Extend the P4a scenario Parquet contract with optional scenario
probabilities. Reduce the existing path-by-step aggregate arrays after policy
aggregation. Use the established output sink and keep the formula engine independent
of reporting. Apply dynamic surrender on opening values in the existing decrement
component, using explicit run parameters supplied by valuation.

**Spec:** UNIT_LINKED product design sections 5.4, 5.5, 5.13 and 7, and the
maintainer's model specification.

## Global constraints

- Work on `ul/p4b-stochastic` in this clone. Keep Git read-only and execute inline.
- Use `uv run --no-sync` for every Python command. Run `uv sync` only if an import fails.
- Keep saved tables and parity tolerances unchanged. Capture the 10,000-policy
  UNIT_LINKED baseline reporting files before changing the decrement component.
- Keep P2b-owned files clear. Use existing `decrements.py` and existing composition
  for dynamic lapse. Record any strictly necessary hook.
- Keep the formula language, IEEE float64, logical policy blocks, and input gate
  invariants in CLAUDE.md. Record test counts and the next step after each task.

## Review focus

1. A weighted tail accounts for the fractional mass at its boundary and ignores
   zero-probability paths. Percentile levels and tail direction are explicit.
2. TERM and UNIT_LINKED use the same summary code. CSVs match byte for byte across
   batch sizes and thread counts.
3. TVOG uses a pathwise PV, its risk-neutral weights, and a deterministic PV at the
   same step and under matching assumptions. The sign is risk-neutral minus reference.
4. Dynamic surrender uses opening balances, leaves the cessation rate and DPF rules
   intact, and gives byte-identical 10,000-policy output when explicitly disabled.

---

### Task 1 — Scenario probabilities and summary reduction

**Files:** `src/avk/esg/{supplied,library}.py`, `src/avk/runs/scenario_statistics.py`,
`tests/esg/test_library.py`, `tests/runs/test_scenario_statistics.py`.

- [x] Write tests for optional Parquet `Weight`, exact round-trip in numeric scenario
  order, absent-column equal weights, and rejection of null, negative, nonfinite,
  month-varying or incorrectly normalized weights. Weights must sum to one within
  float64 roundoff.
- [x] Write tests for the weighted mean, weighted inverse CDF, upper and lower CTE
  at a fractional boundary, ties, zero weights, and undefined output values.
  Use fixed path order for the mean and stable sorted order for the tail. CTE at
  confidence level L averages the worst `1 - L` probability mass in the chosen
  direction. A nonfinite result on a positive-weight path makes that column-step
  undefined for all statistics.
- [x] See red, implement, then run
  `uv run --no-sync pytest tests/esg tests/runs/test_scenario_statistics.py -q`.

### Task 2 — Summary configuration and output

**Files:** `src/avk/runs/{config,check,valuation,scenario_statistics}.py`,
`src/avk/outputs/writers.py`, `tests/runs/test_scenario_summary.py`.

- [x] Test strict validation of `Scenario_Summary` with required `Percentiles`,
  `CTE_Levels`, and `Tail` (`upper` or `lower`). Lists can be empty, contain unique
  numeric levels, and lie within [0, 1] for percentiles and [0, 1) for CTE.
  Test that the input gate rejects requests outside a multi-path Valuation.
- [x] Project TERM and UNIT_LINKED using supplied scenarios. Compare every aggregate
  entry at each step against the path values, check exact ordered schema and file
  reporting, and compare bytes across physical batches and Numba thread counts.
  The summary file is `<PRODUCT>_Base_scenario_summary.csv`, with columns
  `Projection_Step,Output_Column,Mean`, then requested percentile and CTE columns
  in run-file order. Rows follow aggregate schema order, then ascending step.
- [x] See red, implement, then run `uv run --no-sync pytest tests/runs/test_scenario_summary.py -q`.

### Task 3 — TVOG

**Files:** `src/avk/runs/scenario_statistics.py`, `src/avk/api.py`,
`tests/runs/test_tvog.py`.

- [x] Test `avk.api.tvog(scenarios, path_values, certainty_equivalent)` using a
  nonuniform weighted hand calculation, a constant PV, invalid shapes or values,
  and rejection of real-world scenarios. Run TERM for a step-zero MCEV PV under
  supplied risk-neutral paths and its deterministic reference-forward path.
- [x] See red, implement, then run `uv run --no-sync pytest tests/runs/test_tvog.py -q`.
  Log candidate P2b PV and guarantee outputs for later wiring.

### Task 4 — Optional dynamic UNIT_LINKED lapse

**Files:** `src/avk/runs/{config,cases,valuation}.py`,
`src/avk/products/unit_linked/decrements.py`, `tests/unit_linked/test_dynamic_lapse.py`.

- [x] Capture the pre-change 10,000-policy valuation in the clone's scratch folder.
- [x] Test exact surrender rates for less and more valuable guarantees using opening
  fund divided by opening premiums paid as the moneyness proxy. Include active and
  paid-up, floor, cap, zero premiums, basis-specific switches, path divergence,
  unchanged cessation rates, and a cap of one on the adjusted monthly probability.
- [x] Test strict `Dynamic_Lapse` run configuration with all three bases declared,
  each with `Enabled`, `Slope`, `Floor`, `Cap`. Absence disables all bases. The
  multiplier is `clip(1 + Slope * (moneyness - 1), Floor, Cap)` for positive opening
  premiums paid. Apply it only to ordinary monthly surrender.
- [x] See red, implement, then run `uv run --no-sync pytest tests/unit_linked/test_dynamic_lapse.py tests/unit_linked/test_decrements.py -q`.
  Rerun 10,000 policies with all three bases explicitly off. Compare valuation
  reporting CSVs byte for byte and record hashes and timings.

### Task 5 — Tutorial and checks

**Files:** `docs/unit-linked-stochastic.md`, `docs/how-tos.md`, `docs/scenarios.md`,
`CHANGELOG.md`, generated reference if affected.

- [x] Run the tutorial example with generated risk-neutral UNIT_LINKED paths,
  summary, deterministic CE, TVOG on a discounted unit segment and a dynamic
  lapse rerun. Verify referenced output labels and example rankings.
- [x] Run `uv run --no-sync pytest tests/regression/test_documentation.py -q`.
- [x] Run ruff check, ruff format --check, mypy, lint-imports, pytest,
  generate_reference.py --check, generate_ul_fund_slots.py --check,
  check_clean_install.py, uv build, and pytest -m slow. Verify saved files against
  Git and record check results, timings, decisions, and P2b integration points.
