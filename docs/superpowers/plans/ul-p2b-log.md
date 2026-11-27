# UNIT_LINKED P2b implementation log

Branch `claude/nostalgic-shannon-5d7738`, cut from `feature/unit-linked` at 9276bc4.
Work is committed locally for orchestrator review (never pushed).

## Task 1 — Expenses, general fund cashflows and interest

- Files `src/avk/products/unit_linked/{gf_interest,expenses,general_fund,formulas}.py`,
  `src/avk/model/lang.py` (ports `acquisition_cost`, `expense_outgo` on
  `UnitLinkedProduct`), `pyproject.toml` (formula contract, mypy override and import
  edges for the P2b modules), `tests/unit_linked/test_general_fund.py`.
- `uv run --no-sync pytest tests/unit_linked/test_general_fund.py -q` passed 16 tests
  (the module failed on the missing columns before implementation; one test assertion
  was corrected to count paid-up lives that a cessation creates). `pytest tests/unit_linked`
  passed 212. `avk compile UNIT_LINKED`: 695 columns, one pass, cold compile 111 s.
- Decisions:
  - `CaseShocks` binds two Term-only parameters (`lapses_after_payment_term`,
    `renewal_premium_expense_after_payment_term`) that UNIT_LINKED does not have, so the
    UL `ExpenseShocks` component declares the same run parameters and the same
    `inflation_factor` formula rather than reusing it.
  - `expense_add` raises the two fixed per-policy amounts (initial and renewal), as Term
    does; it is an annual per-policy amount, so it is not added to the per-claim expense.
    `expense_mult` scales every expense: initial, renewal, fund and claim.
  - The reserving margin `1 + prudent_margin_expense` loads initial, renewal, fund and
    claim expenses; commission carries none.
  - Claim expenses inflate with `inflation_factor`, as the plan states.
  - Fund expenses read last month's closing unit reserve with no `live` mask, as the plan
    writes it, so a policy settling at step 1 from its valuation-month balances bears one
    month of fund expense on them.
  - Every expense column is masked to zero at step 0 explicitly (an in-force policy at
    duration 1 would otherwise show an initial expense at the valuation instant).
  - Bindings that `UnitLinked` held for later phases and that the new components now own
    (commission table, expense parameters, Inflation, roi/vroi) moved onto those
    components; nothing is declared twice.
- Next: Task 2, reserves and floors.

## Tasks 2 to 4 — Reserves and floors, profit and capital, MCEV

Implemented in one pass and committed together, because each cold compile takes about two
minutes and the three components are composed into `UnitLinked` at the same time. Each
task's tests were written before its module. Each test file ran against the compiled kernel.

- Files `src/avk/products/unit_linked/{reserves,profit,capital,mcev,formulas,fund_slots}.py`,
  `scripts/generate_ul_fund_slots.py` (two new generated totals, `fund_growth_total` and
  `rpu_growth_total`), `src/avk/model/lang.py` (port `coverage_units`), `pyproject.toml`
  (edges), `tests/unit_linked/{conftest,test_reserves,test_profit,test_mcev}.py`.
- `uv run --no-sync pytest tests/unit_linked/test_reserves.py tests/unit_linked/test_profit.py tests/unit_linked/test_mcev.py -q`
  passed 20 tests (7 + 8 + 5). One assertion was fixed: the share of months where a floor
  bites now counts months with lives in force, not the whole 372-month grid.
  `avk compile UNIT_LINKED`: 811 columns in 4 passes, cold compile 121 s.
- Six-policy book at step 0 (reserving): CLASSIC DCF -132,894 with held reserve 15.67 (the
  15-day floor). The DPF policy's DCF is positive (+1,737), from the guarantee cost and
  expenses with only the DPF FMC as income. In every case the reserving total reserve
  exceeds the mc BEL.
- Decisions:
  - `conftest.parity_check` (fixture `assert_parity`) writes per-policy-month grids with
    `Policy_Number` and `Projection_Step` and compares them through
    `avk.testing.parity.compare`, so each policy is measured on its own scale, using the
    CLAUDE.md classes. The tests folder is not a package, so it is a fixture.
  - `gf_reserve_dcf` is not masked at step 0, as the plan states; the held reserve, the
    floor and the revival provision are reported at the valuation instant.
  - `sum_at_risk` = `A_end x sar` + `rpu_sar x R_survival`. The paid-up cohort's aggregate
    sum at risk is scaled to the survivors of the opening cohort. New paid-up entrants'
    cover starts in the next month's `rpu_sar`. At step 0 this is the valuation sum at risk.
  - Unit segment profit is computed on every basis from the basis's own unit flows:
    allocated premium, additions (`addition_outgo`), active and paid-up slot growth and
    the DPF credited return, less admin, mortality and guarantee charges, FMC on all states,
    discontinuance charges, unit-funded exits and withdrawals, less the increase in that
    basis's unit reserve. `total_profit` reads the be unit segment.
  - Capital is computed on every basis, including reserving (not reported there). Part 1
    = factor x (basis unit reserve + reserving non-unit reserve per policy x basis lives).
    Interest on capital is at the basis's general fund rate. `cost_of_capital` in the BE
    chain reads the be capital columns explicitly.
  - MCEV: `mc_reserves` and `mc_increase_in_reserves` are the mc analogues of
    `be_reserves` and `increase_in_reserves`. The plan names only the interest term; the
    profit chain needs both. `pv_premium` discounts the mc basis's premiums, which equal
    the be premiums because both bases carry no decrement margin.
    `gf_bel` = -PV(`mc_net_cf`). This equals the mc `gf_reserve_dcf` (a test asserts it).
    `bel_pp` divides by the unfloored mc lives, as `MarketConsistentValue.bel_pp` does, so
    it is NaN after the last exit.
  - `coverage_units` = be `unit_reserve` x (t > 0): fund value in force across all states.
- Next: Task 5, the output schema.

## Task 5 — Output schema

- Files `src/avk/products/unit_linked/{output_columns,factory,reserves,formulas}.py`,
  `docs/reference/output-columns.md` (regenerated), `tests/unit_linked/test_outputs.py`,
  `tests/unit_linked/test_skeleton_run.py` (now reads the final names).
- `uv run --no-sync pytest tests/unit_linked/test_outputs.py tests/unit_linked/test_skeleton_run.py -q`
  passed 15 tests; `pytest tests/unit_linked` passed 236. Compile: 815 columns, 4 passes.
- Decisions:
  - Layers `reserving`, `BE` and `MC`. `decrements_*` on all three bases;
    `cashflows_*` (premiums, charges by kind and by timing, unit funds by state and
    `unit_reserve`, unit and general-fund benefits by kind, expenses, residual additions,
    interest, net cashflow, the DCF, floor, held reserve, revival provision, non-unit and
    total reserves, the per-policy reserves and `sum_at_risk`) on reserving and BE; the
    profit chain, segment split and capital as `cashflows_*_BE`; `MCEV_*_MC` for the mc
    profit chain, capital, frictional cost, CRNHR, PVFP, PV premium, FCC, VIF, `gf_bel`,
    `bel` and `bel_pp`.
  - The P2a opening-fund entries (`funds_opening_*`) are dropped from the schema: at step 0
    `cashflows_unit_reserve_*` and the per-state fund entries report the same values. The
    columns stay in the model.
  - The per-policy entries aggregate as ratios (`aggregate_ratios`): held amount over the new
    unfloored column `eligible_reserve_lives` on the entry's basis, as the shared factory
    default does for other products. `bel_pp` uses the mc lives and is liability positive.
  - New column `annualised_premium` (the policy field) feeds the seriatim
    `Annualised_premium` at step 0. Every other seriatim value is at step 0 too.
- Next: Task 6, the oracle and the verification checks.
