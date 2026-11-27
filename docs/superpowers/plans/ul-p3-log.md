# UNIT_LINKED P3 implementation log

Branch `claude/ul-p3-compliance-c1cbcb` (contains `4d4e86f` of `feature/unit-linked`).
Plan: `2026-11-27-ul-p3-compliance.md`.

## Decisions made while planning

1. **Scalar projection, not an engine run.** The engine's per-life columns
   (`fund_close_total`, charges per life) are conditional on survival, so they already
   are the no-decrement path and decrements need no zeroing. A compliance run through the
   engine would still need partial withdrawals, mortality, flat extra and guarantee charges
   switched off per case (variant and policy overrides), cold kernel compile (about 70 s)
   per CLI use and a run folder per case. The pure projection mirrors the P2a roll for one
   life and a reconciliation test ties it to the engine (all charges on, 4% and 8%).
2. **Gross return** is the annual-effective rate on every fund; fund alpha is ignored (it is
   an expected-return parameter, not a charge). The monthly rate comes from the P4a library
   `flat` operation.
3. **RIY excludes** mortality charges (with EMR and flat extra), the guarantee charge,
   partial withdrawals, decrements, tax on charges (as the product specification states);
   the illustration keeps every charge but reports the RIY from the compliance run.
4. **Measurement points** are the end of every policy year from year 5 to the term
   (maturity included). The demo `ul_riy_caps` also lists years 1 to 4 at the year-5 cap; those
   rows are not measurement points (a regular-premium policy always breaches in year 1).
5. **Net yield** annual-effective IRR; each instalment at the start of its policy month;
   fund value at the end of month 12n; return of charges and maturity top-ups excluded.
6. **Residual additions** from the sixth anniversary: the product specification requires
   the first five policy years to comply by design, while the model specification starts
   additions at the fifth anniversary; the fifth-year point is therefore a design test.
   Constant `FIRST_ADDITION_YEAR` in one place. Open point for the maintainer.
7. **Addition** in closed form (no goal seek), sequential, credited at the end of month 12n
   pro rata to the slots, so the fund and the general-fund cost are the same amount.
8. **Surrender value** inside the lock-in is the fund less the discontinuance charge, payable
   at lock-in end when the DPF is on; after the lock-in it is the fund.
9. **xlsx**: no writer or dependency exists; CSV only.
10. Not a formula module: no import-linter formula-contract or mypy-formula change.

## Open items

- Wire `residual_additions` into the general fund and the units after P2b merges (the
  orchestrator will message). The formula needs, per policy, the accumulated value of premiums
  at `gross - cap`, which is not recursive across years because the cap changes by year.

## Tasks

### Task 1 - Single-life projection, net yield and RIY (done)

- Files `src/avk/products/unit_linked/illustration.py` (pure numpy: `Case`, `Gross`, `project`,
  `net_yield`, `riy`, `year_end`), `src/avk/runs/ul_compliance.py` (case and schedule builders
  from the bound tables; the orchestration comes in Tasks 3 and 4), `tests/unit_linked/test_illustration.py`.
- `uv run pytest tests/unit_linked/test_illustration.py -q`: 16 passed (141 s including the
  engine kernel cache build). Hand tests: single premium against `(F/P)^(1/n) - 1`; five annual
  instalments with an independent monthly roll and `numpy.roots` for the IRR (both to 1e-10 or
  better); risk-charge exclusion; fund exhaustion; the library `flat` monthly rate equals ours;
  per-life reconciliation with the engine columns on five scenarios x 4% and 8%
  (loyalty, guaranteed additions, rebalance, escalation, guarantee charge, return of charges,
  guarantee top-up, death benefit Types I and II) at 1e-9 relative.
- Decision: `Case.due` and the roll mirror P2a column by column. The case builder
  `case_from_row` reads the prepared contract, so the test feeds the engine and the projection
  the same row. The builders moved forward from Task 3 into this task.
- Next: Task 2, the cap test, status rule and residual additions.

### Task 2 - Cap test and residual additions (done)

- Files `src/avk/products/unit_linked/illustration.py` (`assess`, `Assessment`,
  `BREACH_TOLERANCE`), `tests/unit_linked/test_residual_additions.py`.
- `uv run pytest tests/unit_linked/test_residual_additions.py -q`: 8 passed. Hand cases: single
  premium 100,000 at 8% gross with a 1% cap from year 6: the year-6 addition equals
  `100,000 x 1.07^6 - 95,000 x (1.08 x 0.9865)^6` to 1e-12 relative, RIY after it equals the cap
  to 1e-12, the year-7 addition is positive and smaller than the stand-alone shortfall
  (sequential), a regular-premium case checked with `numpy.roots`.
- Decisions: the addition is credited at the end of month 12n (units added at the year-end
  price), so the units credited and the general-fund cost are the same amount; the status rule
  is `pass`, `pass_with_additions`, `design_fail` (breach before year 6) and `fail`
  (late breach with the feature off or additions that cannot restore the cap). A tolerance of
  1e-12 (rate units) decides a breach.
- Next: Task 3, the demonstration run, API and CLI.

### Task 3 - Compliance demonstration, API and CLI (done)

- Files `src/avk/runs/ul_compliance.py` (`ul_compliance`, `case_for_variant`, `library_gross`,
  `ComplianceReport`), `src/avk/api.py` (`ul_compliance`, `ComplianceReport`), `src/avk/cli.py`
  (`avk ul compliance`), `tests/unit_linked/test_compliance_run.py`.
- `uv run pytest tests/unit_linked/test_compliance_run.py -q`: 16 passed (13 s). `uv run mypy` and
  `ruff check` clean.
- Decisions: cases per variant are each term (default 10, 20, 30), each premium frequency (1, 12;
  one case for single premium) and the lowest and highest annualised premium of the book (the whole
  book's when the variant has no policy), in the selectable fund with the highest FMC, a standard
  life aged 35, full premium payment. Options `--rates --terms --frequencies --premiums --fund`
  override them. Gross returns go through the library `flat` operation. Exit code is 0 unless
  `--strict` and some case fails (a failing design is a result, not a program error).
- **Finding on the invented demo basis** (10,000-policy demo, seed 209, all terms): at the book's
  lowest premiums (about 48,000 to 51,000 a year) every regular-premium variant breaches the
  year-5 cap by design (RIY 4.8% to 7.1% against 4%), because the flat monthly administration
  charge (200 to 250) is 5% or more of such a premium. They pass at the highest premiums
  (about 516,000 to 568,000; one limited-pay case at 8% marginally fails, margin -0.09 points).
  `ULIP_SINGLE` passes with additions; `UL_INVESTMENT_BOND` (UNCAPPED) passes. Not changed here:
  the demo calibration belongs to P1/P2b (`src/avk/testing/demo.py` is off limits to this phase).
- Next: residual additions per policy and year, then Task 4 (benefit illustration).

### Task 4 - Benefit illustration and residual additions per policy (done)

- Files `src/avk/runs/ul_compliance.py` (`ul_illustration`, `ul_residual_additions`,
  `Illustration`, `AdditionsReport`, `ILLUSTRATION_COLUMNS`), `src/avk/products/unit_linked/illustration.py`
  (`project(..., credited=...)`, `Riy.fund` and `Riy.premiums_to_date`), `src/avk/api.py`,
  `src/avk/cli.py` (`avk ul illustration`, `avk ul additions`),
  `tests/unit_linked/test_illustration_output.py` (6), `tests/unit_linked/test_residual_additions.py` (9).
- `uv run pytest tests/unit_linked/test_illustration_output.py tests/unit_linked/test_residual_additions.py -q`: 15 passed.
- Decisions: the illustration keeps every charge and credits the residual additions solved on
  the RIY basis (so the amounts are known before the illustrated fund is rolled); net yield and
  RIY are the RIY-basis figures with the additions credited, `RIY_Before_Additions` the design
  figure. Surrender value inside the lock-in is the fund less the discontinuance charge and
  payable at the lock-in end when the DPF is on; none in the maturity year. Policies whose status
  is 1 or 2 are rejected by the illustration and skipped (and listed) by the additions report.
  The additions report projects each distinct contract once and measures the policy **as sold**
  (from inception), not from its in-force fund value at the valuation date.
- Output format: CSV only. The repository has no xlsx writer and no xlsx dependency; adding one is
  outside this phase.
- Next: Task 5, documentation, CHANGELOG, full checks.

### Task 5 - Documentation, CHANGELOG and full checks (done)

- Files `docs/products/unit-linked-compliance.md` (new), `docs/products/unit-linked.md` (P3
  paragraph and link), `CHANGELOG.md` (one bullet).
- Final verification, run from the worktree root:

| Check | Result |
|---|---|
| `uv run ruff check .` | pass |
| `uv run ruff format --check .` | pass (232 files) |
| `uv run mypy` | pass (137 files) |
| `uv run lint-imports` | 14 contracts kept, 0 broken |
| `uv run pytest` (default) | 463 passed, 9 deselected, 1:17:03 |
| `uv run python scripts/generate_reference.py --check` | current |
| `uv run python scripts/generate_ul_fund_slots.py --check` | current |
| `uv run python scripts/check_clean_install.py` | pass |
| `uv build` | pass |
| `git diff -- tests/saved` | empty (saved results untouched) |
| `uv run pytest -m slow` | not run: no change to a formula, the projection or a kernel; the new modules are outside the formula contract |

- New tests: 47 (16 illustration, 9 residual additions, 16 compliance run, 6 illustration output).
- Open items for the maintainer: wire `residual_additions` into the general fund and units after
  P2b merges; confirm the first addition year (6 here, constant `FIRST_ADDITION_YEAR`); demo
  premiums at the low end design-fail the year-5 cap (calibration belongs to P1/P2b); CSV only.
