# UL P6b: premium funding, settlement option, pension variant — implementation plan

> **For agentic workers:** implement this plan task by task, test first, inline (no
> sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three UNIT_LINKED design features, switched on by `ul_variants` fields:

- **Premium funding benefit (PFB).** On the death of the life assured within the premium
  term, the sum assured is paid at once. The policy stays in force and the insurer pays
  the remaining premiums into the units from the general fund. The fund is paid at
  maturity.
- **Settlement option.** Maturity proceeds are paid in instalments while the units stay
  invested.
- **Pension variant.** No surrender before vesting. At vesting the fund, topped up to the
  guaranteed vesting benefit, splits into a commuted lump sum and an annuity purchase
  amount.

Every new field has a neutral value that leaves each existing variant's results
bit-identical.

**Architecture:** Two new aggregate states with per-slot funds, generated from the
fund-slot template like the RPU slots (design 5.9): the funded state **F** (PFB) and the
settlement state **S**. Pension is a set of switches on existing decrements and a
presentation split of the maturity benefit. Components in
`src/avk/products/unit_linked/`: `premium_funding.py`, `settlement.py` and `pension.py`.
General fund, reserve and output integration uses `@override` on the P2b columns.

**Tech stack:** Python 3.13, the AVK formula language, numba kernels, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md` sections
5.5–5.11 and 7, and the P2a, P2b and P6a plans and logs. The maintainer's specifications in
`C:\avkwt\_ref\` list these features as not offered by the illustrative product. They give
no mechanics, so the decisions below set them. The specifications are read-only and
private: never copy or quote their text. GST on charges and reinsurance are excluded
(design call 10). Top-ups, lifecycle and systematic transfer strategies, and highest NAV are
P6a.

**Prerequisites:** P2b and P6a are merged into `feature/unit-linked`. P6a edits the same
generator template, `features.py`, `validation.py` and the variant table, so start after
it. Cut `ul/p6b-features` from the integration branch. P5 may land before or after. Task 7
covers both orders.

## Decisions (made here; record any deviation in the log)

1. **Field defaults.** New `ul_variants` fields are required, like every variant field (no
   hidden defaults). The demo table and the docs give each existing variant the neutral
   value: `pfb_on 0`, `pfb_sar_rate 0`, `settlement_on 0`, `settlement_instalments 1`,
   `settlement_frequency 12`, `settlement_take_up 0`, `pension_on 0` and
   `pension_commutation_fraction 1`. With neutral values every formula reduces exactly to
   today's. Each new term is gated by a multiplication with a 0/1 flag, or by `if_` on the
   flag, so the gated-off arithmetic yields the old bits. Task 1 proves this.
2. **PFB eligibility.** It applies to active lives who die while premiums remain
   (`pm < ppt_months`), on regular or limited-pay variants. Validation rejects
   `pfb_on 1` with `single_premium 1`, with `pension_on 1`, or with
   `death_benefit_type 2`. PFB on Type II would leave the death lump sum ambiguous, so it
   is rejected rather than guessed. Deaths after the premium term, and deaths in the RPU or
   DPF state, take the ordinary benefit.
3. **PFB death.** The general fund pays the lump sum `max(sa_eff, floor_db)`. The units
   are not paid out. The deceased life's closing slot funds move to the F slots, along with
   its premiums paid to date. Lives move from A to F, so a PFB death is a transfer in the
   decrement accounts, not an exit.
4. **PFB cover charge.** While `pfb_on`, an active life's sum at risk for the mortality
   charge is the death lump sum plus the PV of the remaining premiums, less the fund (floored
   at 0, as Type I). The PV is an annuity-due of the remaining instalments at the annual
   rate `pfb_sar_rate`: `P x (1 - v^n) / (1 - v)` with `v = (1 + pfb_sar_rate)^(-1/freq)`,
   where n is the instalments still payable after this month. At rate 0 the annuity is
   `n x P`.
5. **The F state.** F lives have no deaths, surrenders, partial withdrawals or
   discontinuance. They leave only at maturity. On each due date, the funded premium
   `Instalment_Premium` per F life is an outgo of the general fund, and the
   allocation charge, admin charge, guarantee charge and FMC apply. No mortality charge
   applies, because no cover is left. F lives get no loyalty, booster or guaranteed
   additions, and no return of charges at maturity. Both simplifications are stated. The
   maturity guarantee applies on F's premiums paid, which include the funded premiums.
6. **Funded premiums are internal.** The general fund pays a funded premium into the units.
   It is included in `non_unit_benefit_outgo` (like additions) and kept out of
   `premium_income`. P5's IFRS 17 cashflows exclude it as an internal transfer.
7. **Settlement election** is made at maturity by `settlement_take_up` of the maturing
   active, RPU and F lives. It applies only when `settlement_on`, and the elected unit
   value moves to the S slots. General-fund top-ups (maturity guarantee, returned charges)
   are paid in cash at maturity and never deferred. The first instalment is paid in the
   maturity month. The rest follow every `12 / settlement_frequency` months.
   Instalment j of n pays the S fund after growth divided by the instalments remaining
   (`n - j + 1`), so the last instalment pays out everything. The settlement period is
   `(n - 1) x 12 / settlement_frequency` months.
8. **The S state.** S lives die at the experience mortality rate and the fund is paid on
   death. There is no surrender (commutation) and no mortality, admin or guarantee charge.
   FMC applies and the slots grow at their basis returns. A policy is live for S while
   `term_months < pm <= term_months + settlement period`. Validation checks the horizon the
   way P1 treats the policy term: term plus settlement period must fit inside
   `Projection_Term`. If P1 truncates instead of rejecting, keep its behaviour and log it.
9. **Pension decrements.** After the lock-in, active lives do not surrender
   (`w_surrender x (1 - pension_on)` after the lock-in month). A cessation becomes paid-up.
   Validation requires `rpu_mode 1` and `pw_allowed 0` when `pension_on`. RPU lives in a
   pension variant do not surrender. Inside the lock-in, discontinuance still goes to the
   DPF, and the DPF release at lock-in end is paid as today (regulatory release). The
   product page states it.
10. **Guaranteed vesting benefit** reuses the maturity guarantee fields: `pension_on`
    requires `gmmb_on 1`. The vesting benefit is the maturity benefit P2a already
    computes: units plus the general-fund top-up to `gmmb_premium_multiple x` premiums
    paid, plus any returned charges. No new guarantee formula is added.
11. **Vesting split** is presentation only. `vesting_commutation =
    pension_commutation_fraction x` the vesting benefit, and `annuity_purchase =` the rest,
    paid at vesting as an outgo to the annuity provider. The run does not value the annuity.
    Their total equals the existing maturity benefit columns exactly.
    `settlement_on 1` with `pension_on 1` is rejected.
12. **Pension cover.** A pension variant may have `Sum Assured = 0`. The death benefit is
    then the higher of the fund and the premium floor, through the existing Type I formula.
    Validation skips the regime's minimum cover multiple for `pension_on` variants and still
    requires `Sum Assured >= 0`.
13. **Demo book unchanged.** The demo variant table gains three variants:
    `ULIP_CHILD_PFB`, `ULIP_SETTLEMENT` and `ULIP_PENSION`, with scales in
    `ul_charge_scales` and invented values. The seed-209 book generator does not assign
    them, so the UL saved valuation tables keep their rows and values. A separate example
    book (`examples/ul-features/`, generated by `avk demo generate --product UNIT_LINKED
    --features`) exercises them for tutorials and tests.
14. **Saved results** change only by gaining output columns. New aggregate entries (F and
    S lives, funded premiums, settlement instalments, vesting split) make the UL valuation
    tables wider. Regenerate them. Prove that every pre-existing column is bit-identical to
    the P2b and P6a saved values and every new column is 0 for the demo book. The
    orchestrator gets maintainer approval before the regenerated tables are committed.

## Global constraints

- Every project check in `CLAUDE.md` passes, including `uv run pytest -m slow`. Other
  products' saved results stay byte-identical.
- Formula rules as in P2a and P2b: one docstring and one `return` per column; `if_`,
  `prev`, `nxt`, `at_basis`, `clip`, `min`, `max`; one owner per column; `@override` for
  replacements; JIT-safe divisions (`max(x, 1e-12)` denominators, or an `if_` branch proven
  safe with `NUMBA_DISABLE_JIT=1`).
- F and S slot columns come from `scripts/generate_ul_fund_slots.py` only. Regenerate, and
  the currency test passes. Record compile time before and after. A rise of more than 30%
  goes to the orchestrator before Task 7.
- New formula modules go into the import-linter formula contract and the mypy formula
  override in `pyproject.toml`.
- t = 0 is the valuation instant. Opening F and S balances are zero. A policy already in
  a funded or settlement state at the valuation date is out of scope: P1 has no status
  code for it. Validation keeps rejecting unknown statuses, and the product page says so.
- Keep `docs/superpowers/plans/ul-p6b-log.md` current. Commit at every green task. Never
  push; never touch `main` or `feature/unit-linked`.

## Review focus

1. Neutral defaults: with every new field neutral, all UL columns on all three bases are
   bit-identical to the pre-P6b kernel on the seed-209 demo (compare grids, not
   aggregates).
2. Decrements stay exhaustive with F and S. The accounting holds: A + D + R + F + S +
   cumulative exits = 1. A PFB death is counted once, as a transfer and not an exit.
3. The unit segment profit is still nil every month with each feature on. The unit fund
   reconciles per state: funded premiums in, instalments and deaths out.
4. Settlement timing: the instalment count and dates, the last instalment emptying S, no
   activity after the settlement period, and a policy maturing in the valuation month
   (P2a decision 1) electing settlement.
5. The pension split sums exactly to the maturity benefit, and no surrender payout happens
   after the lock-in.

---

## Fields (`features.py` `VARIANT_FIELDS`, appended after P6a's)

| Field | Rule | Meaning |
|---|---|---|
| pfb_on | flag | 1 the premium funding benefit applies |
| pfb_sar_rate | rate in [0, 1) | Annual rate for the PV of remaining premiums in the PFB sum at risk |
| settlement_on | flag | 1 a share of maturing lives elects instalments |
| settlement_instalments | integer >= 1 | Number of instalments n (1 = lump sum) |
| settlement_frequency | code 1, 2, 4, 12 | Instalments a year |
| settlement_take_up | rate in [0, 1] | Share of maturing lives electing settlement |
| pension_on | flag | 1 pension variant (no surrender before vesting, vesting split) |
| pension_commutation_fraction | rate in [0, 1] | Share of the vesting benefit commuted to cash |

Preparation exposes them as `V_<field>`. Cross-field validation, each check with an exact
message:

- PFB conflicts: decision 2.
- Settlement with pension: rejected.
- Settlement horizon: decision 8.
- `settlement_on 1` requires `settlement_instalments >= 2` (`1` with the flag on is
  rejected as meaningless).
- Pension requirements: decisions 9 and 10.
- Pension minimum cover: decision 12.

## Components and columns (per policy, every basis b)

### Premium funding (`premium_funding.py` plus generated F slots)

- `pfb_eligible = V_pfb_on x paying x (pm < ppt_months)`. `paying` is from P2a.
- `deaths_pfb = deaths_A x pfb_eligible`. `death_unit_A` and `death_non_unit_A` are
  overridden:
  - eligible deaths pay no units, and the lump sum `max(sa_eff, floor_db)` from the
    general fund;
  - other deaths are unchanged.
- `pfb_annuity_pp` is decision 4's annuity-due on the instalments still payable.
- `sar` gains the PFB term through an override of P2a's sum at risk. Type I with PFB
  gives `max(max(sa_eff, floor_db) + pfb_annuity_pp - F3, 0)` when `V_pfb_on`, and
  otherwise P2a's formula.
- Lives: `F_begin = prev(F_end, 0)`, `maturities_F = F_begin x maturity`,
  `F_end = F_begin - maturities_F + deaths_pfb`.
- Per F life (aggregate slots `pfb_k_*`):
  - opening value;
  - a funded premium, allocated by `Fund_k_Allocation` after the allocation charge;
  - admin and guarantee charges, with the P2a exhaustion scale;
  - growth at `fund_k_growth_rate` and the FMC;
  - close = after FMC x (1 - maturity share), plus `deaths_pfb x fund_k_close`.
- Aggregate premium tracking: `pfb_tpp_close = pfb_tpp_open + F_begin x premium_pp +
  deaths_pfb x tpp_pp`, less maturities.
- `pfb_premium_outgo = F_begin x premium_pp` (general fund).
- `pfb_charge_income` is allocation, admin, guarantee and FMC on F.
- Maturity: `maturity_unit_F` (units) and `maturity_guarantee_F` (top-up on F premiums
  paid when `gmmb_on`).

### Settlement (`settlement.py` plus generated S slots)

- `settle_months = (V_settlement_instalments - 1) x 12 / V_settlement_frequency`.
- `settle_live = (pm > term_months) and (pm <= term_months + settle_months) and (t > 0)`.
- `settle_due` is true at months `term_months + j x 12 / freq` for j = 1 .. n - 1.
- `elect = V_settlement_on x V_settlement_take_up`.
- Inflow at maturity: `elect x` the maturing unit value per slot (active, RPU and F).
  Instalment 1 is `inflow / n` in the maturity month. The rest opens S, and the
  corresponding lives move to S.
- `S_begin = prev(S_end, 0)`, `deaths_S = S_begin x q_settle`, where `q_settle` is the
  experience monthly mortality on the basis at the attained age, applied while
  `settle_live`. The P2a `q` is masked off after the term, so a separate column is needed.
  The last instalment closes S: `S_end = S_begin - deaths_S - S_last`.
- Per slot `stl_k_*`: open, growth and FMC, death payout share, instalment
  `stl_k_grown_after_fmc x settle_due / remaining`, close.
  `remaining = n - j + 1` is computed from pm.
- Columns: `settlement_instalment_outgo` (units), `settlement_death_outgo` (units),
  `settlement_fmc_income`. The ordinary maturity unit columns pay `(1 - elect)` of the
  units plus instalment 1.

### Pension (`pension.py`)

- Overrides of P2a surrender columns: active surrenders after the lock-in, and RPU
  surrenders, x `(1 - V_pension_on)`. The rate columns stay and only the exits are gated,
  so the neutral case is bit-identical.
- `vesting_benefit` = maturity benefits paid (units plus top-ups plus returned charges, all
  states) x `V_pension_on`.
- `vesting_commutation = V_pension_commutation_fraction x vesting_benefit`.
- `annuity_purchase = vesting_benefit - vesting_commutation`.

### Integration (`@override` of P2b and P5 columns)

- `unit_reserve` adds the F and S slot totals.
- `coverage_units` (P5's override if present, else P2b's port) adds the F and S funds.
- `charge_income` adds the F charges and the S FMC.
- `charges_start` and `charges_end` take their parts.
- `non_unit_benefit_outgo` adds `pfb_premium_outgo`, the PFB lump sum (inside
  `death_non_unit_A`) and `maturity_guarantee_F`.
- `unit_exit_benefits` adds the F maturity, the settlement instalments and settlement
  deaths.
- `lives_end` adds F and S.
- The reserve lives and decrement outputs include F and S.
- `sum_at_risk` includes the PFB term (P2b's expected sum at risk).
- P5 port lists, if P5 is merged: claims add `maturity_unit_F`, `maturity_guarantee_F`,
  the settlement instalments and deaths, and the PFB lump sum (through `death_non_unit_A`).
  `pfb_premium_outgo` is excluded as internal. Re-run the VFA identity test.

### Outputs (`output_columns.py`)

On every layer: F and S lives (begin and end), PFB deaths, F and S maturities and exits,
funded premiums, F charges, F and S unit funds, settlement instalments, settlement deaths,
the PFB lump sum and annuity term, vesting commutation and annuity purchase. Seriatim
entries are unchanged.

---

### Task 1: Fields, validation, neutral equivalence

**Files:** `src/avk/products/unit_linked/{features,validation,preparation}.py`,
`src/avk/demo/unit_linked.py` (neutral columns plus the three new variants and scales,
which the seed-209 book does not use), `docs/products/unit-linked.md` (variant table);
tests `tests/unit_linked/test_p6b_fields.py`.

- [ ] Tests:
  - Each new field's range and code rule.
  - Every cross-field rule, with exact messages.
  - A variant table missing a new field is rejected (no default).
  - The demo book's variant assignment is unchanged: its policy file is byte-identical
    to before.
- [ ] Implement. `uv run avk check` on the demo passes. Commit; log.

### Task 2: Generator: F and S slot families

**Files:** `scripts/generate_ul_fund_slots.py`, `src/avk/products/unit_linked/fund_slots.py`
(generated), `tests/unit_linked/test_fund_slots_generated.py`.

- [ ] Tests:
  - The generated file is current.
  - F and S columns exist for k = 1..5.
  - Slot totals sum the slots.
  - A zero-allocation, zero-value slot stays exactly zero (as P2a review focus 5).
- [ ] Implement. Record the compile time before and after. Commit; log.

### Task 3: Premium funding benefit

**Files:** `premium_funding.py`, `lives.py` and `benefits.py` overrides, `formulas.py`
(compose); tests `tests/unit_linked/test_premium_funding.py`.

- [ ] One-policy books (monthly and annual pay), each basis:
  - A death in month m < PPT pays `max(sa_eff, floor_db)` from the general fund and no
    units. F lives equal the deaths. F slots open with the deceased lives' funds.
  - Funded premiums fall on the policy's own due dates until the premium term ends, and
    are charged allocation and admin.
  - No mortality charge in F. F lives leave only at maturity, which pays the F fund plus
    the guarantee top-up.
  - The PFB sum at risk equals the hand annuity at rates 0 and 0.05.
  - A death after the premium term takes the ordinary Type I benefit.
  - RPU and DPF deaths are unchanged.
  - Decrements are exhaustive, and the unit fund reconciles in F.
- [ ] Implement. Commit; log.

### Task 4: Settlement option

**Files:** `settlement.py`, `benefits.py` override; tests `tests/unit_linked/test_settlement.py`.

- [ ] One-policy books:
  - n = 5 annual: instalments in maturity months 0, 12, 24, 36 and 48 after maturity.
    Each is the fund after growth divided by the remaining count, and the last empties
    S.
  - Take-up 0.4: 60% of the maturing units are paid at maturity, and 40% / 5 more as
    instalment 1.
  - Deaths during settlement pay the S fund share. No activity after the settlement
    period.
  - The FMC is charged on S.
  - The guarantee top-up is paid in full at maturity.
  - RPU and F maturities elect too.
  - The valuation-month maturity case (P2a decision 1) elects and settles from step 1.
  - The horizon check rejects a term plus settlement period beyond `Projection_Term`.
- [ ] Implement. Commit; log.

### Task 5: Pension variant

**Files:** `pension.py`, the decrement overrides; tests `tests/unit_linked/test_pension.py`.

- [ ] One-policy books:
  - No surrender payout after the lock-in. Cessations go to RPU, and RPU lives do not
    surrender.
  - Inside the lock-in, discontinuance goes to the DPF and is released as before.
  - The vesting benefit equals the existing maturity benefit columns. Commutation plus
    annuity purchase equals it exactly.
  - `Sum Assured = 0` passes validation and the death benefit is `max(fund, floor)`.
  - The guaranteed vesting benefit bites when the fund is below
    `gmmb_premium_multiple x` premiums paid.
- [ ] Implement. Commit; log.

### Task 6: General fund, reserves and outputs

**Files:** `benefits.py`, `general_fund.py`, `reserves.py` and `lives.py` overrides,
`output_columns.py`, `factory.py`, `docs/reference/*` (generated); tests
`tests/unit_linked/test_p6b_integration.py`.

- [ ] Tests:
  - Review focus 1: neutral equivalence over every column on the seed-209 demo, all
    bases.
  - With each feature on, on a 3-policy book:
    - the unit segment profit is nil every month;
    - `charge_income = charges_start + charges_end`;
    - the unit reserve includes F and S;
    - the reserve roll-forward ties;
    - recursion equals summation for the general fund BEL;
    - the schema builds with no duplicate names, and every source column exists in the
      manifest.
- [ ] Implement. Regenerate the reference pages. Commit; log.

### Task 7: P5 interplay

**Files:** `src/avk/products/unit_linked/ifrs17.py` and `stress_sources.py` (only if P5 is
merged); otherwise a note for P5 in the log.

- [ ] If P5 is merged:
  - extend the VFA port lists (Integration above);
  - the VFA identity test passes with each feature on;
  - `death_strain_pp` includes the PFB lump sum and annuity for eligible lives;
  - `sv_non_unit_pp` is nil for F and S.
- [ ] If not: write in `ul-p6b-log.md` the exact list of external and internal flows
  that P5 must classify, and add a test that names `pfb_premium_outgo` as internal, for P5
  to keep.
- [ ] Commit; log.

### Task 8: Oracle extension and spec checks

**Files:** `tests/unit_linked/oracle.py` (no `avk.model` or `avk.products` imports),
`tests/unit_linked/test_oracle_p6b.py`, `tests/unit_linked/test_spec_checks.py`.

- [ ] Write the F and S states and the pension switches from this plan, not from the
  formula code, for three oracle policies (PFB monthly pay, settlement n = 4 quarterly,
  pension with a biting guarantee), every basis and every month. Reconcile column by
  column with `avk.testing.parity` and the `CLAUDE.md` tolerances, never relaxed.
- [ ] Extend the spec checks on the `--features` example book:
  - decrements exhaustive across five states;
  - unit fund reconciliation per state;
  - charge outgo equals charge income;
  - fund nil after maturity, and after the settlement period for S;
  - unit segment profit nil.
- [ ] Batch and thread invariance on the features book. `NUMBA_DISABLE_JIT=1` on its
  20-policy cut.
- [ ] Commit; log.

### Task 9: Saved results, documentation, checks

**Files:** `tests/saved/demo/10000/UNIT_LINKED/valuation/*`, `tests/saved/demo/MANIFEST.json`,
`docs/products/unit-linked.md` (features, states, timing, simplifications; remove the three
features from "Not modelled"), `CHANGELOG.md`, `examples/ul-features/README.md`.

- [ ] Regenerate the UL valuation saved tables at 10k. Write a comparison script and its
  output in the log (decision 14). Every pre-existing column must be bit-identical and
  every new column 0. Other products' files must be unchanged. **Stop before committing
  the saved tables. The orchestrator obtains maintainer approval.**
- [ ] If P5 is merged, regenerate the UL capital, measurement and roll-forward saved modes
  the same way and prove them unchanged in value.
- [ ] Run every project check in `CLAUDE.md` (except `uv sync`) and `pytest -m slow`.
  Record the results, the compile time and the 10k run time. Final report in the log.
  Commit the code.

## Done when

Every task's tests pass and every project check passes. Neutral defaults reproduce every
pre-existing UL column bit for bit. The oracle reconciles the new states. The regenerated
UL saved tables differ only by new zero columns and await maintainer approval.
`ul-p6b-log.md` records decisions, timings and open points.

## Questions for the maintainer

1. PFB: should F lives keep loyalty and booster additions and return of charges, as some
   child plans do? This plan gives them none.
2. PFB on Type II is rejected. Allow it with a lump sum of the sum assured alone?
3. Settlement: allow commutation (surrender) during the settlement period, or deaths only?
4. Pension: is a guaranteed vesting benefit mandatory for every regime, or only under
   `IRDAI_2024` (this plan requires `gmmb_on 1` always)? Should pension variants allow
   partial withdrawals for specified purposes after the lock-in?
5. Should policies already in a funded or settlement state at the valuation date get new
   Policy Status codes (a P1 contract change)?
6. Approve regenerating the UL valuation saved tables with new zero columns.
