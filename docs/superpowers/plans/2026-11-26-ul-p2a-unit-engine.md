# UL P2a: unit engine — implementation plan

> **For agentic workers:** implement this plan task by task, test first, inline (no
> sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The UNIT_LINKED projection up to the unit segment: policy states and decrements,
premiums, the per-slot unit fund roll, every charge, the Discontinued Policy Fund (DPF),
reduced paid-up (RPU) funds, benefits split between units and the general fund, and every
design feature of the variant table. General fund expenses, reserves, profit, capital,
MCEV and the final output schema are P2b.

**Architecture:** Formula components in `src/avk/products/unit_linked/`, composed by the
`UnitLinked` product class (P1 skeleton). Everything that repeats per fund slot is
generated from one template by `scripts/generate_ul_fund_slots.py` into `fund_slots.py`
(slot columns and the slot totals). Bindings declared on the skeleton class move into the
component that reads them; bindings not read until P2b stay declared on the class.

**Tech stack:** Python 3.13, the AVK formula language (`avk.model.lang`), numba kernels,
pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md` (sections
5.4–5.9). P1 contract: `docs/products/unit-linked.md` and the "Interfaces fixed by this
plan" section of `docs/superpowers/plans/2026-11-26-ul-p1-inputs.md` (read
`docs/superpowers/plans/ul-p1-log.md` for the deviations P1 recorded). Source material:
`C:\avkwt\_ref\ul_model_spec.md` sections 6–7 (read-only).

## Global constraints

- Every project check in `CLAUDE.md` passes; existing products' saved results stay byte-identical.
- Formula rules: one docstring and one `return` per column; `if_`, `prev`, `nxt`, `at_basis`, `clip`, `min`, `max` only; columns read at `(t)`. One owner per column; replacements use `@override`; basis differences use `by_basis` or `@on`.
- Every division is safe in JIT and in `NUMBA_DISABLE_JIT=1` mode: denominators are `max(x, 1e-12)` or the division sits inside the taken branch of `if_` only when that is proven safe in pure-Python mode; check how `avk.model.emit` lowers `if_` and `/` before choosing.
- New formula modules are added to the import-linter contract "Formulas only use the authoring API and other formulas" (`source_modules` and `ignore_imports`) and to the mypy formula override in `pyproject.toml`.
- No new run types; UNIT_LINKED stays Valuation-only. Case shocks apply as in Term (`CaseShocks` run parameters for mortality and lapse; expenses are P2b).
- Monthly conversions: a probability `1 - (1 - p)^(1/12)`; a return `(1 + r)^(1/12) - 1`; a charge rate `1 - (1 - c)^(1/12)`.
- t = 0 is the valuation instant: no cashflow, no decrement, no growth, no charge; every state's month-0 closing value equals its opening input.
- The Codex sandbox keeps `.git` read-only: do not run git commands that write; the orchestrator commits. Keep `docs/superpowers/plans/ul-p2a-log.md` current after every green task.

## Review focus

1. A status-2 (RPU) policy at the valuation date: its holdings open the RPU slot funds and its active funds open at zero. Test in Task 6.
2. Charges larger than the fund (small fund, large sum at risk): every deduction scales down so the fund never goes negative and charge income equals what was deducted. Test in Task 4.
3. A discontinuance in the last month of the lock-in, and a DPF policy already past its lock-in at the valuation date: paid in that month, never stranded in the DPF. Test in Task 5.
4. Single premium and limited pay: no cessation decrement after the premium term; the full discontinuance rate applies as surrender. Test in Task 2.
5. A slot with zero allocation and zero value stays exactly zero through rebalancing, growth and charges. Test in Task 3.

---

## Notation (per policy, per basis b unless stated; "pp" = per active life)

`pm = policy_month(t)`, `py = policy_year(t)`, `miy = (pm - 1) % 12 + 1`,
`year_start = (miy == 1) and pm > 1`, `anniversary = (pm % 12 == 0) and pm > 0`,
`term_months = Policy_Term x 12`, `maturity = (pm == term_months)`,
`ppt_months = Premium_Payment_Term x 12`, `in_premium_term = pm <= ppt_months`,
`lock_in = pm <= V_lock_in_months`, `lockin_due = pm >= V_lock_in_months`,
`live = (t > 0) and (pm >= 1) and (pm <= term_months)`.
Status at t = 0: `is_A = Policy_Status == 0`, `is_D = == 1`, `is_R = == 2`.

## Components and columns

### Rates (`decrements.py`)

- `mortality_rate` annual: `min(clip((mortality[age, Gender_Code] x experience_mortality_pct x if_(Smoker_Code == 1, smoker_mortality_loading, 1) + mortality_add[t]) x mortality_mult[t], 0, 1) x EMR x (1 + mad_mortality), 1)`; `mad_mortality = by_basis(reserving=param("prudent_margin_mortality"), be=0, mc=0)`. Flat Extra is a charge loading only (not experience).
- `q = (1 - (1 - mortality_rate)^(1/12)) x live`.
- `discontinuance_rate` annual: `clip((discontinuance[py, Distribution_Channel] + lapse_add[t]) x lapse_mult[t], max(0, table - lapse_maximum_decrease[t]), 1) x (1 + mad_lapse)` capped at 1; `mad_lapse = by_basis(reserving=param("prudent_margin_lapse"), be=0, mc=0)`.
- `paying = in_premium_term and V_single_premium == 0`.
- `surrender_rate` annual: `discontinuance_rate x if_(paying, surrender_share, 1)`; monthly `w_surrender = (1 - (1 - surrender_rate)^(1/12)) x live x (1 - maturity)`.
- `premium_due`: frequency 12 every month; otherwise `pm % (12 / Premium_Frequency) == 1`; single premium only `pm == 1`; always `x live x (in_premium_term or single)`.
- `w_cessation = (1 - (1 - discontinuance_rate x (1 - surrender_share))^(1 / Premium_Frequency)) x premium_due x paying` (0 for single premium).
- `pw_rate` monthly: `(1 - (1 - min(partial_withdrawals[py, channel] x (1 + mad_pw), 1))^(1/12)) x V_pw_allowed x (py >= V_pw_start_year) x live`; `mad_pw = by_basis(reserving=param("prudent_margin_partial_withdrawal"), be=0, mc=0)`.
- `case_mass_lapse` at t = 1 adds to surrenders exactly as `LivesAndExits.lapses` does.

### Lives (`lives.py`, own component; do not reuse `LivesAndExits`)

Active: `A_begin = prev(A_end, is_A)`; `deaths_A = A_begin x q`; `surrenders_A = (A_begin - deaths_A) x w_surrender` (+ mass lapse); `cessations_A = (A_begin - deaths_A - surrenders_A) x w_cessation`; `maturities_A = (A_begin - deaths_A - surrenders_A - cessations_A) x maturity`; `A_end = max(A_begin - deaths_A - surrenders_A - cessations_A - maturities_A, 0)`.

Routing of active discontinuances (`surrenders_A + cessations_A`):
`to_dpf = (surrenders_A + cessations_A) x lock_in x V_dpf_enabled`;
`to_rpu = cessations_A x (1 - lock_in x V_dpf_enabled) x (1 - lock_in) x (V_rpu_mode >= 1)`;
`paid_out_A = surrenders_A + cessations_A - to_dpf - to_rpu`.

DPF: `D_begin = prev(D_end, is_D)`; `deaths_D = D_begin x q`; `lockin_exits_D = (D_begin - deaths_D) x lockin_due + to_dpf x lockin_due`; `D_end = max(D_begin - deaths_D + to_dpf - lockin_exits_D, 0)`.

RPU: `R_begin = prev(R_end, is_R)`; `deaths_R = R_begin x q`; `surrenders_R = (R_begin - deaths_R) x w_surrender_full` where `w_surrender_full` uses the full `discontinuance_rate`; `expiries_R = (R_begin - deaths_R - surrenders_R) x (V_rpu_mode == 2) x live / V_revival_period_months`; `maturities_R = (R_begin - deaths_R - surrenders_R - expiries_R) x maturity`; `R_end = max(R_begin - deaths_R - surrenders_R - expiries_R - maturities_R + to_rpu, 0)`; `R_survival = if_(R_begin > 0, (R_begin - deaths_R - surrenders_R - expiries_R - maturities_R) / max(R_begin, 1e-12), 0)`.

`lives_end = A_end + D_end + R_end` (in force), `maturities = maturities_A + maturities_R`.

### Premiums and per-life history (`premiums.py`)

`premium_pp = Instalment_Premium x premium_due`; `premium_income = premium_pp x A_begin`;
`pac_pp = premium_pp x premium_allocation_rate[py, Variant_Id]`; `allocated_pp = premium_pp - pac_pp`;
`tpp_pp = prev(tpp_pp, Premiums_Paid_To_Date) + premium_pp`;
`instalments_pp = prev(instalments_pp, Instalments_Paid) + premium_due`;
`pw_this_year_pp = if_(year_start, 0, prev(pw_this_year_pp, PW_Current_Year)) + pw_pp`;
`pw_last_year_pp = if_(year_start, prev(pw_this_year_pp, PW_Current_Year), prev(pw_last_year_pp, PW_Previous_Year))`;
cumulative charges per life for return of charges: `mc_cum_pp`, `pac_cum_pp`, `admin_cum_pp` from `MC_To_Date`, `PAC_To_Date`, `Admin_To_Date` plus the month's deducted amounts.

### Unit fund per active life (`fund_slots.py`, generated for k = 1..5, plus totals)

1. `fund_k_open = if_(rebalance, prev(fund_close_total, 0) x Fund_k_Allocation, prev(fund_k_close, Fund_k_Value x is_A))`, `rebalance = V_auto_rebalance x year_start x live`.
2. `fund_k_after_premium = fund_k_open + allocated_pp x Fund_k_Allocation`; `fund_after_premium_total = sum_k`.
3. Requested deductions on the total: `pw_req = fund_after_premium_total x pw_rate`; `admin_req = admin_charge_monthly[py, Variant_Id] x (1 + V_admin_escalation)^(py - 1) x live`; `gc_req = fund_after_premium_total x (1 - (1 - V_guarantee_charge)^(1/12)) x live`; `F3 = fund_after_premium_total - pw_req - admin_req - gc_req`.
4. Sum at risk at F3: `sa_eff = max(Sum_Assured - V_pw_reduces_sa x (pw_this_year_pp_prev + pw_last_year_pp_prev), 0)` using last month's withdrawal totals; `floor_db = V_min_db_premium_multiple x tpp_pp`; Type I `sar = max(max(sa_eff, floor_db) - F3, 0)`; Type II `sar = max(sa_eff, floor_db - F3)`; `mc_rate = mortality_charges[age, Charge_Column] x V_mortality_charge_multiplier x EMR + Flat_Extra x (pm <= Flat_Extra_Term_Months)` (per 1,000 a year); `mc_req = sar x mc_rate / 12000 x live`.
5. `deduction_req = pw_req + admin_req + gc_req + mc_req`; `deduction_scale = if_(deduction_req > fund_after_premium_total, fund_after_premium_total / max(deduction_req, 1e-12), 1)`; each deducted amount (`pw_pp`, `admin_pp`, `gc_pp`, `mc_pp`) is its request times the scale; `fund_k_after_charges = fund_k_after_premium x (1 - deduction_total / max(fund_after_premium_total, 1e-12))` (0 when the total is 0).
6. Additions at `anniversary` (active lives only): `average_fund = (prev(fund_sum_year_pp, FV_Sum_Current_Year) + fund_after_charges_total) / 12` where `fund_sum_year_pp = if_(year_start, 0, prev(fund_sum_year_pp, FV_Sum_Current_Year)) + fund_close_total`; `loyalty_pp = V_loyalty_on x (py >= V_loyalty_start_year) x loyalty_rate[py, Variant_Id] x if_(V_loyalty_basis == 1, average_fund, Annualised_Premium)`; `booster_pp = booster_rate[py, Variant_Id] x average_fund`; `guaranteed_addition_pp = V_guaranteed_addition_rate x Annualised_Premium`; all `x anniversary`; `additions_pp = loyalty_pp + booster_pp + guaranteed_addition_pp`; allocated in proportion to `fund_k_after_charges` (to `Fund_k_Allocation` when the total is 0).
7. `fund_k_growth_rate`: be `sum_j Fund_k_W_j x ret_j[t] + ((1 + Fund_k_Alpha)^(1/12) - 1)`; reserving `(1 + be) x (1 + fund_return_margin)^(1/12) - 1` (`@on("reserving", ...)`); mc `if_(mc_fund_return_source == 0, reference_forward[t], be)` (`@on("mc", ...)`); all `x live`. `fund_k_grown = (fund_k_after_charges + additions_k) x (1 + fund_k_growth_rate)`.
8. `fund_k_fmc = fund_k_grown x (1 - (1 - Fund_k_FMC)^(1/12)) x live`; `fund_k_close = fund_k_grown - fund_k_fmc`; `fund_close_total = sum_k`.

### DPF (`dpf.py`, aggregate expected fund per policy)

`dpf_return = sum_j DPF_W_j x ret_j[t] + ((1 + DPF_Alpha)^(1/12) - 1)` (reserving and mc variants as for funds); `dpf_guaranteed = (1 + R_dpf_min_rate)^(1/12) - 1`; `dpf_open = prev(dpf_close, DPF_Value)`; `dpf_grown = dpf_open x (1 + max(dpf_return, dpf_guaranteed)) x live`-masked; `dpf_fmc = dpf_grown x (1 - (1 - DPF_FMC)^(1/12))`; `dpf_guarantee_cost = dpf_open x max(dpf_guaranteed - dpf_return, 0) x live`; `dpf_after = dpf_grown - dpf_fmc`; `dpf_death_paid = dpf_after x q`; `dpf_inflow = to_dpf x (fund_close_total - disc_charge_pp)`; `dpf_lockin_paid = ((dpf_after - dpf_death_paid) + dpf_inflow) x lockin_due`; `dpf_close = dpf_after - dpf_death_paid + dpf_inflow - dpf_lockin_paid`.

Discontinuance charge per active life: `high = Annualised_Premium > V_disc_ap_threshold`; `disc_charge_pp = min(if_(high, disc_pct_high, disc_pct_low)[py, Variant_Id] x Annualised_Premium, fund_close_total, if_(high, disc_cap_high, disc_cap_low)[py, Variant_Id]) x lock_in`. Income: `(to_dpf + paid_out_A x lock_in) x disc_charge_pp`.

### RPU (`fund_slots.py` slots plus `paid_up.py`, aggregate expected funds)

`rpu_k_open = prev(rpu_k_close, Fund_k_Value x is_R)`; `pusa_open = prev(pusa_close, Paid_Up_Sum_Assured x is_R)`; `rpu_tpp_open = prev(rpu_tpp_close, Premiums_Paid_To_Date x is_R)`. Deductions on the RPU total `R1 = sum_k rpu_k_open`: `rpu_admin_req = R_begin x admin_req_rate`, `rpu_gc_req = R1 x gc rate`; `R3 = R1 - rpu_admin_req - rpu_gc_req`; Type I `rpu_sar = max(max(pusa_open, floor multiple x rpu_tpp_open) - R3, 0)`, Type II `max(pusa_open, floor x rpu_tpp_open - R3)`; `rpu_mc_req = rpu_sar x mc_rate / 12000 x live`; scale and pro-rata deduction as step 5; growth and FMC per slot with the same `fund_k_growth_rate`; `rpu_k_after_fmc`; exits take `1 - R_survival` of each slot; entries add `to_rpu x fund_k_close`:
`rpu_k_close = rpu_k_after_fmc x R_survival + to_rpu x fund_k_close`;
`pusa_close = pusa_open x R_survival + to_rpu x Sum_Assured x instalments_pp / max(Instalments_Payable, 1)`;
`rpu_tpp_close = rpu_tpp_open x R_survival + to_rpu x tpp_pp`. No additions, no premiums, no withdrawals in RPU.

### Benefits (`benefits.py`), positive amounts for the month

| Item | Unit-funded | General fund |
|---|---|---|
| Active death | `deaths_A x fund_close_total` | `deaths_A x (DB - fund_close_total)`, DB Type I `max(sa_eff, fund_close_total, floor_db)`, Type II `max(sa_eff + fund_close_total, floor_db)` |
| Active surrender paid | `paid_out_A x (fund_close_total - disc_charge_pp x lock_in)` | — |
| Active maturity | `maturities_A x fund_close_total` | `maturities_A x (roc_pp + gmmb_pp)`; `roc_pp = V_romc_fraction x mc_cum_pp + V_ropac_fraction x pac_cum_pp + V_roadmin_fraction x admin_cum_pp`; `gmmb_pp = V_gmmb_on x max(V_gmmb_premium_multiple x tpp_pp - fund_close_total - roc_pp, 0)` |
| DPF death and lock-in payout | `dpf_death_paid + dpf_lockin_paid` | `dpf_guarantee_cost` |
| RPU death | `deaths share x rpu total close` | `q x max(DB_R - rpu total close, 0)` aggregated with `pusa` and `rpu_tpp` as for the active death |
| RPU surrender, expiry, maturity | their share of the RPU funds | RPU maturity guarantee `V_gmmb_on x max(multiple x rpu_tpp_open x maturity share - RPU maturity payout, 0)` |
| Additions | — | `A_begin x additions_pp` |
| Partial withdrawals | `A_begin x pw_pp` | — |

### Ports (add `UnitLinkedProduct(Product)` to `avk.model.lang`)

Abstract ports `premium_income`, `charge_income`, `non_unit_benefit_outgo`, `unit_reserve`;
P2b adds `acquisition_cost`, `expense_outgo`, `coverage_units`. `charge_income` = allocation,
admin, mortality, guarantee and FMC charges of active and RPU lives, DPF FMC and
discontinuance charges (all expected totals). `unit_reserve = A_end x fund_close_total +
sum_k rpu_k_close + dpf_close`.

---

### Task 1: Family ports, slot generator and skeleton wiring

**Files:** modify `src/avk/model/lang.py`, `pyproject.toml`; create `scripts/generate_ul_fund_slots.py`, generated `src/avk/products/unit_linked/fund_slots.py`; test `tests/unit_linked/test_fund_slots_generated.py`.

- [ ] Test: running the generator in check mode (`--check`) reports the committed file current; the generated module defines `fund_{k}_close` for k = 1..5 and `fund_close_total`; changing `MAX_FUND_SLOTS` in a temporary copy changes the output (generator reads `bindings.MAX_FUND_SLOTS`).
- [ ] Implement the generator (a string template; deterministic output, ruff-formatted), the family class, and the contract and mypy entries. `uv run avk compile UNIT_LINKED` succeeds. Log; next task.

### Task 2: Rates and lives

**Files:** `decrements.py`, `lives.py`; tests `tests/unit_linked/test_decrements.py`.

- [ ] Tests (one-policy books built from the P1 fixture, run through `avk.api.run` or the executor with a diagnostics grid): monthly q, surrender and cessation values at chosen months equal hand formulas; cessation only on due months within the premium term; single premium and post-term policies have zero cessation and surrender at the full rate (review focus 4); reserving rates exceed be by the margins; `A + D + R` plus cumulative exits equals 1 every month for every state mix (decrements exhaustive); lock-in routing sends discontinuances to D inside the lock-in and to R or payout after it by `rpu_mode`; `dpf_enabled = 0` pays out inside the lock-in.
- [ ] Implement. Run tests and `uv run avk compile UNIT_LINKED`. Log.

### Task 3: Premiums and the active unit fund

**Files:** `premiums.py`, template and generated `fund_slots.py`; test `tests/unit_linked/test_unit_fund.py`.

- [ ] Tests: a one-fund regular policy over 24 months matches a hand roll of steps 1–8 (to 1e-9 relative); two funds with different FMC and asset mixes diverge in value while charges split pro rata; rebalancing restores allocation weights at each anniversary; a zero-allocation empty slot stays exactly 0 (review focus 5); Type I sum at risk is nil once the fund exceeds both the sum assured and the premium floor, and the mortality charge is nil whenever the sum at risk is nil; Type II sum at risk equals `sa_eff` while the fund is above the premium floor; `pw_reduces_sa` lowers `sa_eff` by the current and previous year's withdrawals.
- [ ] Implement. Log.

### Task 4: Charges, fund exhaustion and additions

**Files:** `fund_slots.py` template, `premiums.py`; test `tests/unit_linked/test_charges.py`.

- [ ] Tests: admin escalation `(1 + e)^(py - 1)`; guarantee charge conversion; fund exhaustion (review focus 2): deductions scale so `fund_after_charges_total >= 0` and each reported charge equals its request times the scale; loyalty from `loyalty_start_year` on the average fund (ULIP_CLASSIC: 0.25% at year 10, 0.30% at 11) and on AP for `loyalty_basis 2`; booster and guaranteed additions only at anniversaries; additions allocated pro rata.
- [ ] Implement. Log.

### Task 5: DPF and discontinuance charges

**Files:** `dpf.py`; test `tests/unit_linked/test_dpf.py`.

- [ ] Tests: discontinuance charge follows the scale and AP band (ULIP_CLASSIC year 1: min(6% AP, FV, 6,000) above the threshold); the DPF credits at least the guaranteed rate every month (spec check 10) and the shortfall equals `dpf_guarantee_cost`; with returns above the guarantee no cost arises and the excess stays in the fund; a status-1 policy is paid at the lock-in end; a discontinuance in the lock-in's last month and a status-1 policy already past it are paid at once (review focus 3).
- [ ] Implement. Log.

### Task 6: RPU

**Files:** `paid_up.py`, slot template; test `tests/unit_linked/test_paid_up.py`.

- [ ] Tests: cessation after the lock-in moves fund and lives to R with paid-up SA `SA x instalments paid / payable`; RPU funds keep the policy's fund mix and growth; mortality charge on the paid-up sum at risk; mode 2 exits at `1/revival` a month; mode 0 pays out instead; a status-2 policy opens with its holdings in R and zero active fund (review focus 1).
- [ ] Implement. Log.

### Task 7: Benefits, ports and the unit segment check

**Files:** `benefits.py`, `formulas.py` (compose; class `UnitLinked(..., UnitLinkedProduct)`); `factory.py`/`output_columns.py` (interim aggregate entries per basis: lives by state, premiums, every charge, unit funds by state, unit-funded and general-fund benefits); tests `tests/unit_linked/test_benefits.py`, `tests/unit_linked/test_unit_segment.py`.

- [ ] Tests: Type I and Type II death benefits; maturity pays the fund plus return of charges and the maturity guarantee top-up; unit fund reconciliation every month on all three bases: `unit_reserve(t) = unit_reserve(t-1) + allocated premiums - charges deducted from units - withdrawals + growth - FMC + additions - unit-funded benefits - discontinuance charges + DPF credited return` (exact within the parity money tolerance); fund nil after maturity (spec check 12); the mc basis with `mc_fund_return_source 0` grows every fund at `reference_forward` (spec check 14).
- [ ] Run a 10,000-policy demo valuation; record compile time, run time and column count in the log.
- [ ] Run every project check in `CLAUDE.md` (except `uv sync`) and record results. Log the final report.

## Done when

All tasks pass, every project check passes, and `ul-p2a-log.md` records decisions,
performance numbers and anything handed to P2b.
