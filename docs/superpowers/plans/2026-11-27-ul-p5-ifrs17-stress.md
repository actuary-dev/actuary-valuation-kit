# UL P5: IFRS 17 variable fee approach and stress capital — implementation plan

> **For agentic workers:** implement this plan task by task, test first, inline (no
> sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run UNIT_LINKED under the two run types it rejects today. IFRS17 measures it under
the variable fee approach (VFA): best estimate liability at current rates on the
market-consistent basis, the entity's share of the underlying items, a risk adjustment for
non-financial risk, the CSM at recognition and its roll-forward with release on fund-value
coverage units, onerous groups and the loss component, grouping from the P1 IFRS fields.
StressCapital revalues the general fund BEL under equity, interest, lapse up and down, mass
lapse, expense and mortality stresses. Both work in the measurement and roll-forward modes the
other products already have. New UNIT_LINKED saved results need maintainer approval.

**Architecture:** The run layer gains product-generic seams. A seam is a factory attribute or
method with a default that reproduces today's behaviour exactly. No existing product
overrides a seam, so the GMM and protection results stay byte-identical. UNIT_LINKED overrides
the seams and adds an IFRS adapter component and stress-source columns in
`src/avk/products/unit_linked/`. The model's measure functions (`avk.model.measures`) gain
optional grid keys. They are used only when a product supplies them.

**Tech stack:** Python 3.13, the AVK formula language (`avk.model.lang`), numba kernels,
numpy measures, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md` sections 5.2
(IFRS fields), 5.11, 5.13, 6, 7 and 9. The P2b contract is in
`docs/superpowers/plans/2026-11-26-ul-p2b-results.md` and `ul-p2b-log.md`. Read the
log's decisions and open points for P5 first. Column names below follow the P2b plan and
may have been renamed there. The current IFRS 17 and capital runs are in
`src/avk/runs/{ifrs17,ifrs17_settings,ifrs17_rollforward,ifrs17_rollforward_settings,stress_capital,stresses,cases,capital_settings}.py`
and `src/avk/model/measures/{ifrs17,ifrs17_rollforward,stress}.py`. Source material is the
maintainer's model specification (IFRS 17 measurement, solvency capital, MCEV and
verification sections) in `C:\avkwt\_ref\`. It is read-only and private: never copy or
quote its text into the repository.

**Prerequisite:** P2b is merged into `feature/unit-linked`. Cut the branch `ul/p5-ifrs17`
from it. If P3 or P6b merged first, also read their logs. P3's residual additions and
P6b's funded premiums are internal transfers (Task 5).

## Decisions (made here; record any deviation in the log)

1. **Measurement basis.** IFRS 17 for UNIT_LINKED reads the `mc` basis. With
   `mc_fund_return_source = 0` the underlying items grow at `reference_forward`, which is
   also the discount rate, so the fund is at fair value. The IFRS17 check therefore
   requires `IFRS17.Current_Curve: reference_forward` and `mc_fund_return_source = 0` for
   UNIT_LINKED. The `onerous` current-curve option and the cost of guarantees from
   stochastic sets are out of scope. The certainty-equivalent BEL omits the time value of
   the maturity guarantee and the DPF floor. The product page states this simplification.
2. **No locked-in rates under VFA.** For a VFA product the run uses the current curve
   wherever the GMM uses a locked-in curve: the `locked` BEL, the CSM interest from
   recognition and in the roll-forward, and PV coverage units. `Locked_In_Curves` is
   required only when the run holds a GMM product. The CSM accretion uses the current curve
   of the snapshot it starts from (recognition or opening). Under VFA this accretion is
   part of the change in the entity's share.
3. **Measurement model field.** Every UNIT_LINKED policy in an IFRS17 run must carry
   `Measurement Model = VFA`. GMM for unit-linked is rejected with an exact message. The
   product page records the eligibility assessment against the three direct-participation
   conditions, in our own words, and states that the run does not re-test it per policy.
4. **External cashflows only.** The fulfilment cashflows are what passes between the
   policyholder and the entity: premiums in, and out the unit-funded benefits, the general
   fund top-ups (death above units, maturity guarantee, returned charges), expenses and
   commission. Charges, additions, the DPF guarantee cost, P3 residual additions and P6b
   funded premiums move value between the general fund and the units, so they are
   internal transfers and excluded. Partial withdrawals are paid at the start of the month
   (P2a order), so they enter a start-of-month benefit bucket.
5. **The identity that proves 1–4.** On the mc basis the IFRS BEL at `reference_forward`
   equals the mc unit reserve plus P2b's `gf_bel`, every month, within the money tolerance.
   This is the key test of the phase.
6. **Expenses.** IFRS 17 uses the P2b expense assumptions on the mc basis (commission,
   initial, renewal, fund and claim expenses, all treated as directly attributable). No
   separate IFRS 17 expense tables are added for UNIT_LINKED.
7. **Risk adjustment for non-financial risk only.** The ratio method applies
   `RA_Ratio` to the PV at current rates of the risk outflows: general fund death top-ups
   plus maintenance and claim expenses. Fund payouts carry financial risk only, so they
   are excluded. The cost-of-capital method revalues the non-unit BEL (BEL less the
   underlying items) and rejects a stress set that contains `equity` or `interest` shocks
   for a VFA product.
8. **Entity's share.** It is reported per policy and group as `entity_share`, the PV at
   current rates of the charges the entity expects to deduct. The variable fee is
   `variable_fee = underlying_items - bel_current - ra_current`, which equals the entity
   share less the PV of non-unit outgo less RA. The CSM at recognition is
   `max(variable_fee, 0)` there, the existing `max(-(BEL + RA), 0)`, because the
   underlying items are nil at issue. The loss component is `max(BEL + RA, 0)`.
9. **Coverage units.** The default is fund value in force: active, paid-up and DPF unit
   funds, the P2b `coverage_units` port. The product parameter `ifrs_coverage_units_basis`
   is 0 for fund value and 1 for fund value plus the sum at risk. P5 overrides the port
   with `@override` and the demo uses 0.
10. **Grouping.** Portfolio is `Portfolio` and the annual cohort is `Issue Cohort`.
    Preparation derives profitability as `IFRS_Profitability` from `Profitability Group`:
    0 is `onerous`, 1 is `no_significant_possibility` and 2 is `other`. The settings check
    accepts the third value, `no_significant_possibility`, for every product. No existing
    data holds it, so nothing changes. At recognition, new business is `onerous` when
    FCF > 0. Otherwise it keeps its input group, and input 0 becomes `other`. Legal Entity
    and Transition Approach are not group keys. In-force contracts are measured from the
    valuation date. Transition is a simplification that the run states in its notes and the
    product page flags.
11. **New-business recognition snapshots.** GMM re-checks the valuation-date data at the
    month end before issue. This is wrong for UNIT_LINKED, whose data is a state: units,
    history and status. A factory seam `recognition_tables(...)` returns the issue-state
    policy and holdings rows. These have Duration 0, status 0, zero units in each held fund
    with the same allocation, zero history, the snapshot's Valuation Date and Fund Entry
    Date equal to the start date. Every row is transformed so that the run's masks still
    align. Rows not issued that month are discarded after measurement, as today.
12. **Capital measure for unit-linked.** Unit assets move with the unit reserve, so own
    funds change only through the non-unit liability. StressCapital and the cost-of-capital
    RA therefore revalue the general fund BEL per policy held (`gf_bel_pp`, mc basis) for
    every stress. This also covers equity, whose fall in unit value is matched by the fall
    in unit assets. Mass lapse uses the non-unit surrender strain `sv_non_unit_pp`, minus
    the discontinuance charge inside the lock-in and 0 otherwise. Catastrophe uses the
    non-unit death strain `death_strain_pp`. Operational risk, when set, uses the total
    liability (unit reserve plus `gf_bel`).
13. **Equity shock.** A new shock target `equity` takes `Additive` only. It is an
    immediate fall, in [0, 1), in the four equity asset classes (`eq_large`, `eq_mid`,
    `eq_small`, `eq_global`) at the valuation instant. Gold and real assets are not
    shocked. The fall is applied at step 1 to the opening value of each active and
    paid-up slot, at `1 - fall x (equity weight of the fund)`. Premiums invested in month 1
    buy at the fallen price and are not shocked. The DPF takes the fall through its
    month-1 return, so the 4% floor bears it, as shareholders bear the guarantee cost
    today. The run parameter is `equity_fall`, neutral 0.0. A product whose factory does
    not list `equity` in `supported_shocks` rejects the shock.
14. **Interest shock.** The existing `interest` shock shifts every `interest_rates`
    column and regenerates the scenarios. On the mc basis the funds then grow and discount
    at the shocked `reference_forward`, so only the non-unit BEL moves. Asset-class returns
    are not shocked.
15. **Lapse stresses** shock the discontinuance rate (surrender and cessation) through the
    P2a `lapse_add`/`lapse_mult`/`lapse_maximum_decrease` parameters. Partial withdrawal
    rates are not shocked.
16. **Capital stays separate from the valuation run.** The valuation run's factor-based
    solvency capital and MCEV CRNHR (P2b) are unchanged, and so are UL valuation saved
    results. StressCapital reports stress-based capital and its cost of capital on its
    own. The product page reconciles the two, and a test proves that the StressCapital base
    BEL equals the valuation mc `gf_bel` per policy.
17. **Demo stress preset** `src/avk/presets/solvency_ii_unit_linked.yaml` holds the life
    risks of the existing life preset plus equity (39% and 49% as two cases of one risk,
    the larger taken) and interest (up and down 1 percentage point flat, labelled a
    demonstration, not the regulatory term structure). It has one labelled correlation
    matrix. Life cells come from the existing preset. Market–life cells are 0.25. Equity
    and interest are 0.5, the down-scenario choice. The comments say the single-level
    matrix simplifies the two-level standard formula. Settings are portfolio aggregation,
    a cost-of-capital rate of 0.06 and `Discount_Curve: reference_forward`. An IFRS-only
    preset `solvency_ii_unit_linked_ifrs.yaml` drops equity and interest.

## Global constraints

- Every project check in `CLAUDE.md` passes, including `uv run pytest -m slow`.
- Existing products' saved results stay byte-identical in every mode. This includes
  measurement, roll-forward and capital, which go through the seams changed here. The
  UNIT_LINKED valuation saved tables from P2b also stay byte-identical: P5 adds kernel
  columns but no valuation output entries.
- A seam default must reproduce today's arrays bit for bit. Do not add a zero array where
  the code used to add nothing (`x + 0.0` turns -0.0 into 0.0). Branch on the key's presence.
- Formula rules as in P2a and P2b: one docstring and one `return` per column; `if_`,
  `prev`, `nxt`, `at_basis`, `clip`, `min`, `max`; columns read at `(t)`; one owner per
  column; `@override` for replacements; JIT-safe divisions. New formula modules go into the
  import-linter formula contract and the mypy formula override.
- `avk.model` stays free of product knowledge. Measure functions take arrays and flags,
  never product codes.
- The `equity_fall` edit goes into the fund-slot template in
  `scripts/generate_ul_fund_slots.py`, never into the generated file. Regenerate, and the
  currency test passes.
- Keep `docs/superpowers/plans/ul-p5-log.md` current (task, files, tests and counts,
  decisions, next step). Commit work-in-progress on your branch at every green task. Never
  push; never touch `main` or `feature/unit-linked`.

## Review focus

1. Seam defaults: GMM measurement, roll-forward and every product's StressCapital produce
   byte-identical saved tables (`tests/regression/test_demo_suite.py` plus the 100k slow
   suite).
2. The VFA identity (decision 5) holds every month on a mixed book: active, DPF, RPU,
   guarantee and withdrawal policies.
3. Recognition snapshots for UNIT_LINKED project from issue with nil underlying items, and
   the CSM at recognition equals the PV of expected charges less non-unit outgo and RA.
4. The roll-forward absorbs investment experience into the CSM. With closing units 10%
   above expectation, the CSM's experience movement equals the increase in the entity's
   share less the change in non-unit FCF. Under the GMM it would not do this.
5. Equity capital is positive and equals the rise in `gf_bel` (lost future charges and the
   extra sum at risk). The total BEL falls under the shock, so measuring total BEL would
   give zero capital. A test proves the measure is the non-unit one.

---

## Seams (run layer; defaults keep today's behaviour)

| Seam | Where | Default | UNIT_LINKED |
|---|---|---|---|
| `ProductFactory.measurement_model: str` | `products/registry.py` | `"GMM"` | `"VFA"` |
| `ProductFactory.capital_sources() -> dict[str, tuple[str, str \| None]]` | `products/registry.py`, read by `stress_capital._columns`, `ifrs17._risk_grids` and `_measurement_names` | today's names on `be`: `bel_pp`, `bel`, `premium_income`, `lives_end`, `lives_begin`, `maturities`, `sum_assured`, `reins_sum_assured`, optional `claim_stock`, `sv` | `bel_pp → gf_bel_pp`, `bel → capital_bel_total`, `sv → sv_non_unit_pp`, `sum_assured → death_strain_pp`, `reins_sum_assured → no_reinsurance`, lives and premium on `mc` |
| `ProductFactory.supported_shocks: frozenset[str]` | `runs/cases.py` check | `SHOCK_NAMES` without `equity` | adds `equity` |
| `ProductFactory.recognition_tables(policies, companions, snapshot_date)` | `runs/ifrs17._prepare` via `check._check_single` | returns its inputs unchanged | issue-state rows (decision 11) |
| roll-forward opening sources | `ifrs17_rollforward_settings.configure_rollforward` | policy table only | policy table plus `companion_tables` |
| `PRODUCT_ORDER` | `ifrs17_rollforward.py` | five products | appends `UNIT_LINKED` |
| VFA port map | `runs/ifrs17.py` (`PORTS` keyed by measurement model) | today's `PORTS` | decision 4 ports on `mc` (Task 5) |
| `VariableFeeApproach(Regime)` | `model/regimes.py` | — | ports `premium_income`, `charge_income`, `non_unit_benefit_outgo`, `unit_reserve`, `coverage_units`, `expense_outgo`, `acquisition_cost` |

`measurement()` in `avk/model/measures/ifrs17.py` gains optional grid keys. Each enters only
when present:

- `claims_start`: start-of-month benefits, in the BEL with start timing and in the
  released outflows' start bucket.
- `risk_outflows`: replaces `claims` as the ratio-RA base.
- `underlying_items`, `charges_start`, `charges_end`: add `underlying_items`,
  `entity_share` (PV of the charges at current rates, each with its timing) and
  `variable_fee`.

`_rates` returns `locked = current` broadcast for a VFA product.

---

### Task 1: Run-layer seams with unchanged defaults

**Files:** `src/avk/products/registry.py`, `src/avk/model/regimes.py`,
`src/avk/model/measures/ifrs17.py`, `src/avk/runs/{ifrs17,ifrs17_settings,ifrs17_rollforward,ifrs17_rollforward_settings,stress_capital,cases,check}.py`;
tests `tests/runs/test_measurement_seams.py` (new) and the existing IFRS 17, capital and
demo-suite tests.

- [ ] Tests first:
  - `measurement()` with and without each optional key. Without the keys every output is
    bit-identical to the current function: compare with a frozen copy in the test on
    random grids, using `np.array_equal`. With the keys, the start-timed claims and the
    RA base give the hand-computed values.
  - `VariableFeeApproach().applicability` lists the missing ports.
  - `capital_sources()` default equals today's `_columns` names.
  - `supported_shocks` rejects `equity` for TERM with
    `"<case>: equity shock is not supported by TERM"`.
  - `no_significant_possibility` is accepted as a profitability value.
- [ ] Implement the seams. `measurement_settings` selects the regime from
  `factory.measurement_model`, and `Locked_In_Curves` becomes optional when every product
  is VFA. For VFA, `_rates`, `_recognise` and `build_rollforward` take the current curve of
  the relevant snapshot report in place of `locked_rates`. Add `equity_fall: 0.0` to
  `case_parameters`. In `_stress_parameters`, combine the base and stress values as
  `1 - (1 - a)(1 - b)`.
- [ ] Run `uv run pytest tests/regression/test_demo_suite.py` and the IFRS 17 and capital
  test modules: every existing saved table is byte-identical. Commit; log.

### Task 2: Equity shock in the unit engine

**Files:** `scripts/generate_ul_fund_slots.py`, `src/avk/products/unit_linked/{fund_slots,dpf,paid_up,formulas}.py`,
`src/avk/runs/cases.py` (parse `equity`: `Additive` in [0, 1), no `Multiplicative`, no
window); tests `tests/unit_linked/test_equity_shock.py`.

- [ ] Tests on one-policy books for each basis:
  - With `equity_fall = 0.3`, slot k's step-1 opening value is
    `prev close x (1 - 0.3 x sum of eq weights_k)`. A 100% debt fund is unchanged.
  - The month-1 premium allocation is unshocked.
  - An RPU slot is shocked the same way.
  - The DPF's month-1 return includes the fall and the guarantee cost rises by the
    shortfall.
  - With `equity_fall = 0` every UL column is bit-identical to the unshocked kernel
    (compare all 655+ columns).
  - A case with `equity: {Multiplicative: 0.6}` is rejected with an exact message.
- [ ] Implement in the template; regenerate (`--check` passes). Commit; log.

### Task 3: UL stress sources and the StressCapital run

**Files:** `src/avk/products/unit_linked/stress_sources.py` (new component),
`formulas.py`, `factory.py` (`capital_sources`, `supported_shocks`, run types),
`preparation.py` (`RUN_TYPES` gains `StressCapital` and `IFRS17`; keep the exact error for
anything else), `src/avk/presets/solvency_ii_unit_linked.yaml` and
`solvency_ii_unit_linked_ifrs.yaml`, `src/avk/presets/README.md`; tests
`tests/unit_linked/test_stress_capital.py`.

Columns (mc basis unless stated):

- `gf_bel_pp = gf_bel / reserve lives`, the non-unit BEL per policy held: NaN at 0/0 as
  `bel_pp` elsewhere, and positive when the general fund owes.
- `sv_non_unit_pp = -A_end x disc_charge_pp x lock_in / reserve lives`.
- `death_strain_pp` is the general-fund death top-up per policy held if every life in
  force died at the end of month t. It covers active lives from P2a's sum at risk and
  closing fund, and paid-up lives from the aggregate paid-up cover, floor and funds. DPF
  lives contribute nothing.
- `capital_bel_total = -(unit_reserve + gf_bel)` (income positive, as the operational
  measure expects).
- `no_reinsurance = 0.0`.
- Lives (`lives_end`, `lives_begin` if absent from P2a) and `premium_income` are read on
  mc.

- [ ] Tests:
  - On the 1,000-policy demo with the UL preset, the run writes the aggregate, seriatim
    and `cases_impact` files. The base `gf_bel_pp` equals the valuation run's mc `gf_bel`
    per policy (decision 16).
  - Mortality x1.15, expense and lapse-up capital are positive at step 1. Lapse up is a
    loss because exits remove future charges: assert its sign.
  - Lapse down is computed and `lapse` is the maximum of the three lapse risks.
  - Mass lapse equals `0.40 x max(sv_non_unit_pp - gf_bel_pp, 0) x inforce`.
  - Equity capital is positive and equals the rise in `gf_bel` times inforce, while the
    total BEL falls under the shock (review focus 5).
  - Interest up and down: unit reserve per policy unchanged on the mc basis, and capital is
    the maximum of the two.
  - Batch and thread invariance of the capital outputs.
- [ ] Implement. Commit; log.

### Task 4: IFRS settings, grouping and the measurement-model check

**Files:** `src/avk/products/unit_linked/{preparation,validation,factory}.py`,
`src/avk/runs/ifrs17_settings.py`, `docs/products/unit-linked.md` (eligibility
assessment); tests `tests/unit_linked/test_ifrs17_settings.py`.

- [ ] Tests (exact messages):
  - A policy with `Measurement Model = GMM` in an IFRS17 run is rejected.
  - `Current_Curve` other than `reference_forward` is rejected for UNIT_LINKED.
  - `mc_fund_return_source = 1` is rejected.
  - A cost-of-capital RA stress set with `equity` or `interest` is rejected for
    UNIT_LINKED.
  - `IFRS_Profitability` maps 0, 1 and 2 to the three strings.
  - The group keys come from `Portfolio` and `Issue Cohort`. Check that both survive
    preparation into `report.points.frame`. If they do not, pass them through as unread
    text fields.
  - The run notes contain the transition simplification.
  - Locked-in curves may be omitted for a UL-only run.
- [ ] Implement. Commit; log.

### Task 5: VFA measurement adapter

**Files:** `src/avk/products/unit_linked/ifrs17.py` (component `UnitLinkedIfrsMeasurement`,
product `IfrsUnitLinked`), `factory.py` (`IfrsUnitLinkedFactory`, `measurement_model`),
`src/avk/runs/check.py` (`run_factory` maps UNIT_LINKED for IFRS17), the
`ifrs_coverage_units_basis` parameter in the demo basis, `coverage_units` `@override`;
tests `tests/unit_linked/test_ifrs17_vfa.py`.

Ports (all `at_basis("mc", ...)`):

- `measurement_premiums = premium_income`.
- `measurement_claims` = `unit_exit_benefits` + `death_non_unit_A` + `death_non_unit_R` +
  `return_of_charges` + `maturity_guarantee_A` + `maturity_guarantee_R` (end of month).
- `measurement_claims_start = partial_withdrawal_outgo`.
- `measurement_acquisition = acquisition_cost`.
- `measurement_maintenance = expense_outgo`.
- `measurement_claim_expense = claim_expenses`.
- `measurement_risk_outflows = death_non_unit_A + death_non_unit_R + expense_outgo +
  claim_expenses`.
- `measurement_underlying_items = unit_reserve`.
- `measurement_charges_start = charges_start`, `measurement_charges_end = charges_end`.
- `measurement_coverage = coverage_units`.
- `measurement_ri_premiums = measurement_ri_recoveries = 0.0`.

The VFA port map adds `inforce`, `maturities` and `commissions` on mc. It has no
`onerous_rate` or `ifrs_expense_capital`.

If P3 or P6b is merged, list their internal transfers (residual additions, funded
premiums) in a test as excluded, and add P6b's settlement and funded-state payouts to the
claims.

- [ ] Tests:
  - The VFA identity (decision 5), at every month on a 20-policy mixed book and on the
    1,000-policy demo.
  - `entity_share` equals the hand PV of the charges with start and end timing.
  - `variable_fee = underlying_items - bel_current - ra_current`.
  - The ratio RA equals `RA_Ratio x` the PV of the risk outflows, and excludes fund payouts.
  - Coverage-unit basis 0 equals the fund value in force; basis 1 adds the sum at risk.
  - An IFRS17 measurement run on the 1,000-policy demo writes the policy, group and
    aggregate files. Every UL policy is in exactly one group.
- [ ] Implement. Commit; log.

### Task 6: Recognition of new business

**Files:** `src/avk/products/unit_linked/factory.py` (`recognition_tables`),
`preparation.py` and `validation.py`, with the snapshot flag in `PreparationConfig`. At the
snapshot, a start date in the month after the snapshot date is allowed and gives Duration
0. Test `tests/unit_linked/test_ifrs17_recognition.py`.

- [ ] Tests:
  - For a policy issued inside the reporting period, the snapshot model point has zero
    units, zero history, status 0 and Duration 0.
  - The snapshot projects policy month 1 at step 1 (first premium, initial expense).
  - `underlying_items` is 0 at recognition, and `csm_at_recognition = max(entity_share -
    PV non-unit outgo - RA, 0)` by hand.
  - A variant priced to lose money (high commission) is `onerous` with
    `loss_component = BEL + RA`.
  - An input group 1 policy that is profitable stays `no_significant_possibility`.
  - The CSM interest at recognition accretes at the snapshot's `reference_forward`.
  - Rows not issued in the month do not reach the output.
- [ ] Implement. Commit; log.

### Task 7: Roll-forward mode

**Files:** `src/avk/runs/ifrs17_rollforward_settings.py` (companion tables in
`Policy_Data`), `src/avk/demo/unit_linked_book.py` (opening and closing policy and
holdings files, opening balances), `src/avk/runs/ifrs17_rollforward.py`; test
`tests/unit_linked/test_ifrs17_rollforward.py`.

- [ ] Tests:
  - `Policy_Data` must name both `policies_ul` and `policy_funds_ul`, with an exact
    message when one is missing.
  - On a 200-policy book over 6 months: every movement stage is present; opening +
    movements = closing for CSM and loss component (money tolerance); the release
    fraction equals provided / (provided + future) recomputed from the output; interest
    uses the current curve of the opening snapshot.
  - Review focus 4: closing holdings 10% above expectation and same assumptions. The
    experience-stage CSM movement is positive and equals
    `-(prior_existing_fcf - expected_fcf)` for a non-onerous group.
  - An onerous group's loss component releases on the outflow fraction.
- [ ] Implement. Commit; log.

### Task 8: Demo configs, outputs and saved results

**Files:** `src/avk/demo/unit_linked_book.py` (`capital.json`, `measurement.json`,
`rollforward.json`, `balances.csv`, opening and closing files, IFRS field values with all
three profitability groups and at least three cohorts), `src/avk/testing/demo.py` (UL modes
`("valuation", "capital", "measurement", "rollforward")`),
`tests/regression/test_demo_suite.py`, `tests/saved/demo/10000/UNIT_LINKED/{capital,measurement,rollforward}/*`,
`tests/saved/demo/MANIFEST.json`, `docs/reference/*` (generated).

- [ ] Generate only the three new UL modes at 10,000. Compare the manifest with git. Only
  new entries may appear, and every existing saved file's hash must be unchanged, including
  UL valuation.
- [ ] Add the three modes to `test_public_10k`.
- [ ] Write the saved-results summary in the log: rows and columns per file, and at the
  valuation date by group the BEL, RA, entity share, CSM, loss component and the stress
  capital per risk. **Stop before committing the saved tables. The orchestrator obtains
  maintainer approval for the new saved modes.** Commit the code; log.

### Task 9: Oracle extension

**Files:** `tests/unit_linked/oracle.py` (still no `avk.model` or `avk.products` imports),
`tests/unit_linked/test_oracle_ifrs17.py`, `tests/unit_linked/test_oracle_capital.py`.

- [ ] Write from this plan and the design, not from the formula code:
  - The IFRS cashflows by decision 4 for the P2b oracle's policies plus one
    new-business policy.
  - `bel_current`, ratio RA, `underlying_items`, `entity_share` and `variable_fee` at
    every month.
  - The CSM at recognition and PV coverage units.
  - The stressed mc projections for mortality, lapse up and down, expense, equity 0.39 and
    interest ±0.01, giving the per-month capital per risk, and mass lapse by the immediate
    formula.
- [ ] Reconcile with the IFRS17 diagnostics stream and the StressCapital diagnostics,
  every column, using `avk.testing.parity` with the `CLAUDE.md` tolerances, never relaxed.
  A disagreement is a defect on one side: find it, fix it, log it.
- [ ] Commit; log.

### Task 10: Documentation and checks

**Files:** `docs/products/unit-linked.md` (run types, VFA approach and eligibility,
cashflow classification, RA, coverage units, recognition, roll-forward, stresses and
equity mechanics, capital measure, simplifications), `docs/` run-type pages where they list
supported products, `CHANGELOG.md`.

- [ ] Remove the "Valuation run type only" statement. Record the compile time of
  `IfrsUnitLinked` and the 10,000-policy run times per mode.
- [ ] Run every project check in `CLAUDE.md` (except `uv sync`), `pytest -m slow`, and a
  `NUMBA_DISABLE_JIT=1` run of `tests/unit_linked/test_ifrs17_vfa.py` and
  `test_equity_shock.py`. Record the results.
- [ ] Final report in the log: per task, test counts, checks, the saved-results summary,
  decisions, and open points for P6b. Commit.

## Done when

Every task's tests pass and every project check passes. Every existing saved table is
byte-identical. The VFA identity holds. The oracle reconciles the IFRS 17 and capital
columns it computes. UNIT_LINKED capital, measurement and roll-forward results are
generated and awaiting maintainer approval. `ul-p5-log.md` records decisions, timings and
open points.

## Questions for the maintainer

1. Approve new UNIT_LINKED saved modes `capital`, `measurement` and `rollforward` at 10k.
2. Certainty-equivalent VFA without the time value of the maturity guarantee and DPF floor.
   Accept, or add a stochastic TVOG adjustment from P4b later?
3. Should Legal Entity form part of the portfolio key?
4. Keep the valuation run's factor-based CRNHR, or replace it in MCEV with the stress-based
   cost of non-hedgeable capital (mortality, lapse, expense and catastrophe only)?
5. Should lapse stresses also shock partial withdrawal take-up?
6. Demonstration calibration: equity 39%/49%, flat ±1 pp interest, single-level
   correlation matrix. Acceptable for a teaching preset?
