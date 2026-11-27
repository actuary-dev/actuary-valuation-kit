# UL P2b: general fund and results — implementation plan

> **For agentic workers:** implement this plan task by task, test first, inline (no
> sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the first UNIT_LINKED delivery on top of the P2a unit engine: general
fund (non-unit) cashflows, the unit and general fund reserves with their floors, the profit
signature with the unit/non-unit split, solvency capital, MCEV on the `mc` basis, the final
output schema, an independent scalar oracle, the model specification's verification
checks, UNIT_LINKED saved results, documentation and a performance record.

**Architecture:** New formula components in `src/avk/products/unit_linked/`, composed into
the `UnitLinked` product class after the P2a components. Shared components in
`src/avk/products/common/` are reused only where their semantics match exactly (design
section 10); otherwise write a UL component and keep the shared output names
(`be_net_cf`, `profit_before_tax`, `pvfp`, ...) so reports read alike across products.

**Tech stack:** Python 3.13, the AVK formula language (`avk.model.lang`), numba kernels,
pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md` sections
5.10–5.13 and 6. P2a contract: `docs/superpowers/plans/2026-11-26-ul-p2a-unit-engine.md`
and `docs/superpowers/plans/ul-p2a-log.md` (read its decisions and "open points for P2b"
first: column names below follow the P2a plan and may have been renamed there). Source
material: `C:\avkwt\_ref\ul_model_spec.md` sections 8, 10–13 and 15 (read-only; private:
never copy or quote its text into the repository).

## Global constraints

- Every project check in `CLAUDE.md` passes, including `uv run pytest -m slow`; existing
  products' saved results stay byte-identical (do not regenerate them).
- Formula rules as in P2a: one docstring and one `return` per column; `if_`, `prev`,
  `nxt`, `at_basis`, `clip`, `min`, `max`; columns read at `(t)`; one owner per column;
  `@override` for replacements; basis differences through `by_basis` or `@on`; every
  division safe in JIT and in `NUMBA_DISABLE_JIT=1` mode.
- New formula modules go into the import-linter formula contract and the mypy formula
  override in `pyproject.toml`.
- Sign convention as elsewhere: `net_cashflows` is outgo less income (positive when the
  reserve pays out); `be_net_cf` and the profit chain are income positive.
- t = 0 is the valuation instant: no cashflow; reserves, capital and present values are
  reported there (reserves stand at the end of month t).
- UNIT_LINKED stays Valuation-only. Case shocks follow Term (`CaseShocks`): expense
  add/mult, inflation windows, mortality and lapse shocks.
- Commit work-in-progress on your branch at every green task; keep
  `docs/superpowers/plans/ul-p2b-log.md` current (task, files, tests and counts,
  decisions, next step). Never push; never touch `main` or `feature/unit-linked`.

## Review focus

1. The held general fund reserve is `max(DCF, 0, floor)` with the floor = reserve floor
   days / 365 x the annualised mortality charge on the lives in force; the DCF is usually
   negative on the demo basis, so the zero or charge floor bites (assert this happens).
2. The unit segment profit is nil every month on every basis (within the parity money
   tolerance), and unit + non-unit segment profit equals the total profit.
3. The reserve roll-forward ties on the best-estimate chain: opening non-unit reserve +
   BE net cashflow + interest on the reserve - profit before tax = closing reserve.
4. MCEV uses the `mc` basis (funds growing at `reference_forward` when
   `mc_fund_return_source = 0`), not the BE path re-discounted; the frictional cost is the
   tax and profit-transfer leakage on interest earned by capital, not the lock-up.
5. Present values by backward recursion equal discounted summation computed in the test
   by a forward product of discount factors.

---

## Components and columns (per policy; "b" = every basis unless stated)

### Interest (`gf_interest.py`)

`interest_rate = by_basis(reserving=scen("vroi"), be=scen("roi"), mc=scen("reference_forward"))`.
Do not reuse `ValuationInterest` (it has no `mc` entry).

### Expenses and commission (`expenses.py`)

All on the basis's lives; the reserving basis loads every expense (not commission) by
`1 + prudent_margin_expense`; shocks as in Term (`expense_add` on fixed amounts,
`expense_mult` on every expense). `inflation_factor` from `CaseShocks`.

- `commissions = commission_rate[py, Distribution_Channel] x premium_income` (table
  `commissions_ul`, year-channel lookup as P1 declared).
- `initial_expense = (initial_fixed + initial_pct_premium x premium_pp +
  initial_pct_sa x Sum_Assured) x A_begin x (pm == 1)`: only new business pays it.
- `renewal_expenses = renewal_fixed / 12 x inflation_factor x (A_begin + R_begin + D_begin)
  x (py >= 2) x live`: every policy in force bears maintenance, whatever its state.
- `fund_expenses = fund_expense_rate / 12 x opening unit reserve` (the unit reserve at the
  end of the previous month; zero at t = 0).
- `claim_expenses = claim_expense x inflation_factor x (deaths_A + deaths_R + deaths_D)`.
- Ports: `acquisition_cost = commissions + initial_expense`;
  `expense_outgo = renewal_expenses + fund_expenses`.

### General fund cashflows (`general_fund.py`)

- `residual_additions = 0.0` (a column of its own; P3 replaces it with `@override`).
- Start-of-month charge income `charges_start` = allocation, admin, mortality and
  guarantee charges (active and RPU); end-of-month `charges_end` = FMC (active, RPU, DPF)
  and discontinuance charges; `charges_start + charges_end == charge_income` (test).
- `interest_earning_cashflow = charges_start - acquisition_cost - expense_outgo`.
- `interest_on_cashflows = interest_earning_cashflow x interest_rate[t] x (t > 0)`.
- `net_cashflows = -(charge_income - acquisition_cost - expense_outgo - claim_expenses -
  non_unit_benefit_outgo - residual_additions + interest_on_cashflows) x (t > 0)`.

### Reserves (`reserves.py`)

- `pv_net_cashflows(t) = (nxt(pv_net_cashflows, 0) + net_cashflows(t)) / (1 + interest_rate[t])`.
- `gf_reserve_dcf = nxt(pv_net_cashflows, 0)` (end of month t, shown at t = 0).
- `annual_mortality_charge = 12 x nxt(mortality_charge_income, 0)` (the charge on the lives
  in force at the end of month t); `gf_reserve_floor = reserve_floor_days / 365 x
  annual_mortality_charge`.
- `gf_reserve_held = max(gf_reserve_dcf, 0, gf_reserve_floor)`.
- `revival_provision = revival_strain_dpf x dpf_close + revival_strain_rpu x rpu_close_total`.
- `non_unit_reserve = gf_reserve_held + revival_provision`;
  `total_reserve = unit_reserve + non_unit_reserve`.
- `reserve_lives = max(lives_end + maturities, 1e-6)`; per policy:
  `gf_reserve_pp`, `non_unit_reserve_pp`, `total_reserve_pp` (each divided by it).
- `sum_at_risk` (expected total for the lives in force at the end of the month): active
  `A_end x sar_pp` plus the RPU sum at risk, from P2a's columns.

### Profit signature (`profit.py`, best-estimate chain read explicitly)

Mirror `ProfitSignature` names without reinsurance:

- `be_net_cf = -at_basis("be", net_cashflows)`.
- `be_reserves = at_basis("reserving", non_unit_reserve_pp) x at_basis("be", lives_end + maturities)` x (t > 0) — the held non-unit reserve for the BE lives (the unit reserve is the
  unit segment's own and is excluded).
- `increase_in_reserves`, `interest_on_reserves` (at `roi`), `profit_before_tax`,
  `profit_transfer`, `tax`, `net_profit_before_sm`, `cost_of_capital`,
  `net_profit_after_sm`: exactly the shared chain's formulas.
- Segment split: `unit_segment_profit` = (allocated premium + additions credited + fund
  growth + DPF credited return) - (charges deducted from units + unit-funded benefits +
  withdrawals) - increase in the BE unit reserve; `non_unit_segment_profit =
  profit_before_tax`; `total_profit = unit_segment_profit + non_unit_segment_profit`.

### Solvency capital (`capital.py`, own component)

- `guaranteed = V_gmmb_on == 1` selects the with-guarantee factors
  (`reserve_capital_factor_guarantee`, `sar_capital_factor_guarantee`), otherwise the
  no-guarantee ones.
- On basis b (computed for `be` and `mc`; reserving output not required):
  `part1_sm = factor1 x (unit_reserve + be_reserves_b) x target_capital_ratio` where
  `be_reserves_b` is the non-unit reserve scaled to basis b's lives;
  `part2_sm = factor2 x sum_at_risk x target_capital_ratio x (pm < term_months)`;
  `required_solvency_capital = if_(t > 0, max(part1_sm + part2_sm, 0), 0)`;
  `increase_in_solvency_capital`, `interest_on_solvency_capital` (at the basis's
  `interest_rate`) as in `SolvencyCapital`. Keep these names so the profit chain reads them.

### MCEV (`mcev.py`, the `mc` basis)

- `mc_net_cf = -at_basis("mc", net_cashflows)` (its interest is already at
  `reference_forward`); `mc_reserves` = reserving non-unit reserve per policy x mc lives;
  `mcev_interest_on_reserve` at `reference_forward`; `mcev_profit_before_tax`,
  `mcev_profit_transfer`, `mcev_tax`, `mcev_net_profit` as in `MarketConsistentValue`.
- `pvfp` (variant A, at `reference_forward`), `pv_premium` (variant B).
- `frictional_cost = interest_on_sm_mc x (tax_rate + (1 - tax_rate) x profit_transfer_rate)`
  with `interest_on_sm_mc` on the mc capital at `reference_forward`; `fcc` = its PV.
- `crnhr_charge = cost_of_capital_rate / 12 x mc required_solvency_capital`; `crnhr` = PV.
- `vif = pvfp - fcc - crnhr`.
- `gf_bel = -nxt(pv of mc net_cashflows)` (non-unit best-estimate liability at t; positive
  when the general fund owes) and `bel = unit_reserve_mc + gf_bel`; `bel_pp` divided by mc
  lives as `MarketConsistentValue.bel_pp` does.
- `coverage_units` port = active plus RPU plus DPF fund value in force (for P5).

### Outputs (`output_columns.py`, `factory.output_schema`)

Layers `reserving`, `BE`, `MC` (`LAYERS` gains `"mc": "MC"`). Aggregate entries:

- `decrements_*` per layer: lives by state (begin and end), deaths, surrenders, cessations,
  maturities, transfers to DPF and RPU, DPF lock-in exits, RPU expiries, total in force.
- `cashflows_*` reserving and BE: premiums, allocated premium, each charge by kind,
  charge income total, unit funds by state and `unit_reserve`, unit-funded and general
  fund benefits by kind, additions, partial withdrawals, commissions, each expense,
  residual additions, DPF guarantee cost, interest, `net_cashflows`, `gf_reserve_dcf`,
  `gf_reserve_floor`, `gf_reserve_held`, `revival_provision`, `total_reserve`, the per
  policy reserves, `sum_at_risk`.
- BE only: the profit chain, the segment split, capital.
- `MCEV_*_MC`: the mc profit chain, `pvfp`, `pv_premium`, `fcc`, `crnhr`, `vif`,
  `gf_bel`, `bel`, `bel_pp`.
- Seriatim at step 0: `unit_reserve`, `gf_reserve_held`, `total_reserve` (reserving),
  `bel`, `pvfp`, `vif` (mc), `sum_at_risk` (BE), `Annualised_premium`.
- Keys: `Policy_Number`, `Policy_Month` (integer), `Calendar_Month`, `Projection_Step`.
  Replace P2a's interim entries; keep the skeleton's opening-fund entries only if still
  meaningful.

---

### Task 1: Expenses, general fund cashflows and interest

**Files:** `gf_interest.py`, `expenses.py`, `general_fund.py`, `formulas.py` (compose),
`pyproject.toml`; test `tests/unit_linked/test_general_fund.py`.

- [ ] Tests on one-policy books: initial expense only at pm 1; renewal from policy year 2
  on all three states, inflated and shocked like Term; the reserving basis loads expenses
  by the margin and not commission; charge income split start/end sums to the total; the
  net cashflow equals the hand formula at chosen months on each basis; `residual_additions`
  is zero.
- [ ] Implement. `uv run avk compile UNIT_LINKED`. Commit; log.

### Task 2: Reserves and floors

**Files:** `reserves.py`; test `tests/unit_linked/test_reserves.py`.

- [ ] Tests: recursion equals discounted summation (review focus 5); held reserve never
  below zero or the floor, and the floor equals the hand value at t = 0; on the demo
  basis the DCF is negative for an ULIP_CLASSIC policy in mid-term so a floor bites
  (review focus 1); revival provision on DPF and RPU funds; total = unit + non-unit;
  per-policy reserves divide by the reserve lives.
- [ ] Implement. Commit; log.

### Task 3: Profit, segments and capital

**Files:** `profit.py`, `capital.py`; test `tests/unit_linked/test_profit.py`.

- [ ] Tests: unit segment profit nil every month on every basis and the total equals the
  sum of segments (review focus 2); reserve roll-forward ties (review focus 3); the profit
  chain arithmetic (transfer before tax, as the shared chain); capital uses the
  with-guarantee factors for ULIP_MATURITY_GUARANTEE and the others elsewhere; capital is
  zero at t = 0 and stops at maturity.
- [ ] Implement. Commit; log.

### Task 4: MCEV

**Files:** `mcev.py`; test `tests/unit_linked/test_mcev.py`.

- [ ] Tests: with `mc_fund_return_source = 0` every fund grows at `reference_forward` on
  the mc basis (spec check 14) and `pvfp` is computed from that path, not the BE one
  (review focus 4); the frictional cost equals the leakage formula; VIF = PVFP - FCC -
  CRNHR; `bel` = mc unit reserve + `gf_bel` at t = 0; with `mc_fund_return_source = 1`
  the mc fund path equals the BE path.
- [ ] Implement. Commit; log.

### Task 5: Output schema

**Files:** `output_columns.py`, `factory.py`; test `tests/unit_linked/test_outputs.py`.

- [ ] Tests: the schema builds (no duplicate names), every source column exists in the
  compiled manifest for its basis, the seriatim file has one row per policy with the
  step-0 values, and the detailed per-policy-month output (`Output_seriatim_cf_flag = 1`)
  writes for a 3-policy book.
- [ ] Implement. Regenerate reference pages (`uv run python scripts/generate_reference.py`).
  Commit; log.

### Task 6: Independent oracle and verification checks

**Files:** `tests/unit_linked/oracle.py` (plain Python and polars only: no `avk.model`,
no `avk.products` imports), `tests/unit_linked/test_oracle.py`,
`tests/unit_linked/test_spec_checks.py`.

- [ ] Write the oracle from the design and the P2a and P2b plans, not from the formula
  code: four policies chosen to cover ULIP_CLASSIC Type I with two funds and loyalty,
  a Type II policy with partial withdrawals and `pw_reduces_sa`, a status-1 DPF policy
  inside the lock-in, a status-2 RPU policy (add a fifth for ULIP_MATURITY_GUARANTEE if
  the four leave the guarantee untested). Every basis, every month; reconcile the
  per-policy-month output column by column with `avk.testing.parity` (the tolerances in
  `CLAUDE.md`, never relaxed). Any disagreement is a defect in one side: find which,
  fix it, and log it.
- [ ] Spec checks on a 1,000-policy demo book, each its own test: decrements exhaustive;
  unit fund reconciliation; charge outgo equals charge income item by item; sum at risk
  never negative and nil above the floors; no mortality charge without sum at risk;
  recursion equals summation; floors hold; reserve roll-forward ties; reserving total
  reserve at least the BEL (log the per-case margin); DPF never below the guaranteed rate;
  fund nil after maturity; unit segment profit nil; mc funds grow at the risk-free rate.
- [ ] Batch and thread invariance on the UL demo (batch sizes 1,000 and 10,000, threads 1
  and 4: byte-identical outputs) and a `NUMBA_DISABLE_JIT=1` run of a 20-policy book
  equal to the JIT run within tolerance.
- [ ] Stochastic smoke: generate 8 multi-asset paths with `avk scenarios generate`
  (P4a), run a 200-policy UL valuation on them, and check that each path's mc-basis
  check holds and the outputs carry the `Scenario` column. No saved results.
- [ ] Commit; log.

### Task 7: Saved results, documentation, performance

**Files:** `src/avk/testing/demo.py`, `tests/regression/test_demo_suite.py`,
`tests/saved/demo/10000/UNIT_LINKED/valuation/*`, `tests/saved/demo/MANIFEST.json`,
`docs/products/unit-linked.md`, `docs/reference/*` (generated), `CHANGELOG.md`.

- [ ] `avk.testing.demo`: add `--products` (default: the existing five) and UNIT_LINKED
  with modes `("valuation",)`; generate only UNIT_LINKED at 10,000 (existing tables and
  their manifest entries must not change: diff the manifest and check every other saved
  file's hash is unchanged).
- [ ] Add UNIT_LINKED valuation to the 10k demo suite (`test_public_10k`); leave the 100k
  slow suite to the existing products unless its run time stays under five minutes.
- [ ] Docs: complete `docs/products/unit-linked.md` (general fund, reserves and floors,
  profit and segments, capital, MCEV, outputs, the checks, known simplifications,
  stochastic use) and the CHANGELOG entry.
- [ ] Performance: time compile and a 10,000- and 100,000-policy valuation; record them in
  the log and the product page.
- [ ] Run every project check in `CLAUDE.md` (except `uv sync`) and `pytest -m slow`;
  record results. Final report in the log: per task, counts, checks, the saved-results
  summary (rows, columns, valuation-date totals: unit reserve, held non-unit reserve,
  BEL, PVFP, VIF), decisions, and open points for P3, P4b and P5.

## Done when

All tasks pass, every project check passes, the oracle reconciles every column it
computes, UNIT_LINKED saved results exist at 10k with the existing ones byte-identical,
and `ul-p2b-log.md` records decisions, timings and open points.
