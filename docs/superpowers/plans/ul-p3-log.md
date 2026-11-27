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
