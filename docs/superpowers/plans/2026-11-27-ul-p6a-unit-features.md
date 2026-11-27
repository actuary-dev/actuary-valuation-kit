# UL P6a: unit-engine features — implementation plan

> **For agentic workers:** Use superpowers:executing-plans, inline and test first.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project top-up premiums and cover, lifecycle and systematic fund
transfers, and path-dependent highest-NAV maturity guarantees.

**Architecture:** The adapter resolves the new policy and holding inputs to model
points. The active unit roll applies switches at opening and credits top-ups at
premium allocation. Generated slot formulas track tagged top-up holdings, fund
prices and guarantee state. Unit-segment ports deliver premiums, charges and
maturity guarantee costs to the general fund.

**Tech stack:** Python 3.14, Polars, the AVK formula language, Numba, pytest and uv.

**Spec:** UNIT_LINKED design §§5.2–5.8, 7 and 9, P1 contract, P2a timing conventions,
the maintainer's product specification and the maintainer's model specification.

## Global constraints

- Use `uv run --no-sync`; all new tests also run with `NUMBA_DISABLE_JIT=1`.
- Keep the generated slots current, use one owner per formula, and validate
  before projection. Keep formula arithmetic safe in interpreted mode.
- Preserve the seeded demo's policy and holding files and its aggregate and
  seriatim bytes. New demo basis rows carry off values.
- Keep the existing saved result files byte-identical. Leave Git metadata alone.
  Log each green step. Keep general-fund components and decrements out of the diff.

## Review focus

1. Locked top-up money remains in the units through deductions, growth and
   switches. Partial withdrawals are limited to unlocked money.
2. Purchases, internal switches, switch charges and expected exits reconcile.
   No switch earns an external premium or generates a policyholder payout.
3. NAV peaks are fund-specific, path-specific and independent of unit purchases.
   The valuation-date holding price seed applies to both active and paid-up units.
4. Default output headers and values match the captured valuation byte for byte.

### Task 1: Top-up premium, cover and withdrawal lock

**Files:** UL validation, preparation, formula inputs, premiums, benefits,
paid-up, DPF, slot generator, demo basis and top-up tests.

- [x] Write failing tests. An active policy pays 200 monthly with a one-off 300
  in month 72. At a 10% allocation charge it credits 180 then 450, split 40%/60%
  as 72/108 and 180/270. A 1.25 multiple adds 250 then 875 to cover and carries
  through paid-up conversion. Zero base premium gives 200 and 500 gross premium
  and 20 and 50 allocation-charge income before weighting by opening lives.
  A 180 locked balance plus 100 base with a 100% withdrawal request releases
  100 now and 180 when its lock expires. Reject negative, non-finite, missing
  enabled fields, inconsistent dates, and a cap breach.
- [x] Add policy fields `Single Top-Up Premium`, `Single Top-Up Policy Month`,
  `Regular Top-Up Premium` per base premium due, `Top-Up Premiums Paid To Date`,
  `Last Top-Up Policy Month`, and holding `Top-Up Units`. Accept legacy omission
  with the variant off. Validate supplied values even when off and reject nonzero
  top-up amounts/state on an off variant. Use a new `topup_allocation_rate` scale
  and variant fields `topup_on`, `topup_sa_multiple`, `topup_lock_in_months`.
- [x] Pay single top-ups in their specified future policy month and regular
  top-ups when the regular base premium is due. Include gross top-ups in total
  premiums and PAC in charge income and refund history. Add the top-up cover
  before applying the death benefit type and floor. Opening total premium history
  already includes top-ups. Carry top-up cover unreduced to the paid-up cohort.
- [x] Use one policy-level top-up lock, renewed by each contribution. The
  contribution month and the following N−1 months are locked. All top-up units
  are tagged throughout the active roll. Locked units may fund charges and
  switch internally. The lock restricts partial withdrawals, with death, maturity
  and full discontinuance using the existing settlement rules. Apply the
  discontinuance charge only against base-premium fund value. Run and log tests.

### Task 2: Lifecycle and systematic transfer strategies

**Files:** UL strategy preparation and validation, factory, feature fields,
benefits, slot generator, demo basis and strategy tests.

- [x] Write failing tests. Lifecycle starts with equity/debt 800/200 and a 70%
  equity target, giving 700/300. The following age target is 40%, giving
  400/600. Cover the reverse index for years to maturity. An STP transfers
  25% of a 600 source (150), or a fixed 200, to two targets at 25%/75%. On a
  150 switch a fixed charge of 10 leaves 140 allocated (35/105). A 60 tagged
  top-up balance in a 600 source loses 15 of its value on a 150 transfer,
  with 14 credited to the targets after the charge. Cover exhaustion, no
  switch at step 0, invalid source/target slots, weights and switch caps.
- [x] Add `Fund Strategy` (optional policy integer, default 0) and a required
  `ul_strategies` year-key table with a strategy-0 off row. Use the source slot,
  schedule/share, amount and five debt/target weights. Slots follow P1 fund-code
  ordering. Lifecycle uses one equity source and a basket of debt destinations;
  STP uses one source and one or more destinations. The lifecycle target applies
  at the first live step and at policy-year start. Persist the last schedule
  row beyond its last index. Validate codes, schedule direction, amounts, target
  weights and fund eligibility. `switch_charge` is an amount per switched month,
  limited by the size of the switch and validated against the regime cap.
- [x] Switch the opening active balances, preserving the top-up proportion within
  each source and crediting targets net of the switch charge. Strategy overrides
  anniversary auto-rebalancing. Add the switch charge to charge income. Run and
  log tests.

### Task 3: Highest-NAV window and maturity shortfall

**Files:** UL preparation, variant fields, slot generator, benefits,
output columns and factory, valuation schema hook and highest-NAV tests.

- [x] Write failing tests. With 10 units at NAV 10 and seed 12, paths with
  net NAVs 15 then 9 and 11 then 13 give unit payouts 90 and 130 and separate
  shortfalls 60 and 0. A late first window month excludes a pre-window spike.
  A policy maturing at valuation with 5 units and price/seed 10/12 settles for
  50 units value and 10 general-fund cost in step 1. Repeat in paid-up status.
  Test fund-type discrimination, FMC, mortality weighting, and the named
  valuation output through the regular run entry point.
- [x] Prepare opening price and guarantee type from the fund universe and use
  `highest_nav_start_month` (0 off) through term end. NAV is net of FMC and uses
  each basis's existing fund return. Use the holding's `Guaranteed Unit Price`
  as the step-0 peak. Validate relevant seeds and window timing. At maturity,
  add the guarantee excess to the unit-segment non-unit port and credit it
  toward any policy-level GMMB floor. Add the separate per-basis output for books
  with an enabled highest-NAV holding through a default-preserving schema hook.
  Run and log tests.

### Task 4: Compatibility, documentation and checks

- [x] Document input formats, timing, settlement and default behavior. Compare
  generated demo policies and holdings and the two valuation CSVs against the
  before run using bytes and SHA-256. Verify the saved result tree against HEAD.
- [x] Run all required checks, the new tests with JIT disabled, and the scope
  review. Record commands, results and any remaining limitations in the log.
