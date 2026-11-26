# Unit-linked product (UNIT_LINKED): design

Status: draft for maintainer approval, 2026-11-26 · Owner: orchestrator session ·
Tracker: [unit-linked status](../plans/2026-11-26-unit-linked-status.md)

Source material (kept outside the public repository, read-only):
`C:\avkwt\_ref\ul_product_spec.md`, `C:\avkwt\_ref\ul_model_spec.md` (text of the
maintainer's illustrative ULIP product and model specifications) and the workbook
`C:\avkwt\_ref\India_IRDAI_ULEndowment_UnitPlusGeneralFundDCF.xlsm`
(`C:\avkwt\_ref\xlsx_dump.py <xlsm> <Sheet> ...` prints a sheet). Do not copy these
files, or text from them, into the repository.

## 1. Intent

Add a generic, broad unit-linked product to Actuary Valuation Kit. The base is a
regular, limited or single premium unit-linked endowment (ULIP) whose mechanics
follow the source specifications (IRDAI 2024: Type I/II death benefit, five-year
lock-in, Discontinued Policy Fund, reduced paid-up, charge caps). It is
generalised so that one compiled product covers many real designs:

- a wide fund universe modelled on real unit-linked fund ranges;
- policies holding several funds at once;
- product design features that are switched on and off by data (guarantees,
  loyalty additions, return of charges, partial withdrawals, paid-up behaviour,
  regulatory caps);
- fund growth driven by asset-class market variables, so the same kernel runs a
  deterministic path or a supplied set of stochastic scenarios.

## 2. Goals, non-goals, anti-goals

Goals

- G1 Product code `UNIT_LINKED` registered in `ProductRegistry.default()`;
  `avk check` and the Valuation run type work for deterministic and supplied
  multi-path scenario sets.
- G2 Policy-level and fund-level inputs (section 5.2): one row per policy in the
  policy table and one row per policy-fund holding in the fund holdings table, with
  key consistency validated. Up to `MAX_FUND_SLOTS = 5` funds per policy.
- G3 A fund universe table (about 22 funds) with charges, asset mixes and flags.
- G4 A product variant table whose fields switch design features on and off.
- G5 Regulatory caps as data keyed by regime (`IRDAI_2024`, `UNCAPPED`), checked
  before projection.
- G6 Three bases: `reserving`, `be`, `mc` (market consistent). Unit reserve plus
  general fund reserve with regulatory floors; best-estimate profit signature with
  unit and non-unit segments; solvency capital; MCEV present values.
- G7 Stochastic-ready: every market quantity is a declared scenario variable.
- G8 Invented demo book and basis, saved results, an independent scalar oracle,
  the specification's verification checks as tests, and user documentation.
- G9 Input data rich enough for retrospective calculations (premiums, charges,
  withdrawals and additions to date) and IFRS 17 grouping (portfolio, annual
  cohort, profitability group, transition approach), even where this release does
  not yet consume a field.

Non-goals for the first delivery (later phases, section 7)

IFRS 17 variable fee approach, stress-capital run type, built-in stochastic
generator and scenario summaries, reduction-in-yield residual additions and
benefit illustrations, lifecycle and systematic-transfer strategies, top-ups,
premium funding benefit, highest-NAV guarantee mechanics, settlement option,
pension variant, GST on charges, reinsurance, switching behaviour.

Anti-goals

- Any change to an existing product's saved results (they stay byte-identical).
- Relaxing any parity tolerance.
- Per-policy Python loops, hidden defaults, missing values turned into zero.
- The numerical core (`avk.model`) learning about unit-linked business.
- A blended single fund standing in for several funds.
- Real policy or assumption data, or the maintainer's source documents, in the
  repository.

## 3. Constraints

- Formula language: a column is a docstring and one `return` expression; `if_`,
  `prev`, `nxt`, `at_basis` only; columns read at `(t)`; no dimensions. Fund
  slots are therefore written out per slot by a generator script (section 4).
- float64, IEEE arithmetic, no fastmath; logical blocks of 1024 policies.
- Inputs load explicitly and validate before projection; strict public formats.
- Import-linter contracts stay unchanged (products may not import esg/runs/...).
- Assumption spec covers exactly the bindings of the composition; bindings that a
  later phase will read are declared on the product class (precedent: `Term.support`).
- Existing saved demo tables stay byte-identical; new UNIT_LINKED saved tables
  need maintainer approval with an explanation of the results.
- The repository is public.

## 4. Approaches considered

Multi-fund representation

| Approach | Trade-off | Decision |
|---|---|---|
| A. Fixed fund slots 1..N, per-slot formulas generated from one template (`scripts/generate_ul_fund_slots.py` writes `src/avk/products/unit_linked/fund_slots.py`; a test asserts the file is current) | No core change; exact per-fund growth and FMC; unused slots still cost compute; N is a constant (regenerate to change) | **Chosen**, N = 5 |
| B. Add a fund dimension to the compiler and emitter (`dims`) | Arbitrary fund counts; large core change touching determinism and every kernel | Rejected now; slot naming keeps a path to it |
| C. Blended single fund | Wrong once funds grow at different rates (model spec 7.2) | Rejected |
| D. One projected row per policy-fund | Sum at risk and pro-rata deductions need the policy total | Rejected |

Fund returns

| Approach | Decision |
|---|---|
| Ten asset-class return scenario variables; a fund's monthly return is its asset-mix weighted sum plus a fund alpha | **Chosen**: ESG size independent of fund count; matches how ESGs and real fund mandates work |
| One scenario variable per fund | Rejected: a scenario variable cannot be indexed by a policy field, and the ESG grows with the fund range |

Inputs: one CSV (or Parquet) per logical table through registered public formats
(**chosen**, repository convention); a single workbook was rejected (no xlsx reader,
strict typed formats).

## 5. Design

### 5.1 Code layout

```
src/avk/products/unit_linked/
  __init__.py
  bindings.py        asset classes, MAX_FUND_SLOTS, status codes, field and table names
  features.py        variant field names, meanings and allowed values (one source of truth)
  formulas.py        components and the UnitLinked product class
  fund_slots.py      GENERATED per-slot components (do not edit)
  factory.py         UnitLinkedFactory: assumption spec, adapter, validator, schema
  preparation.py     vectorised model points: holdings pivot into slots, fund attributes
  validation.py      policy, holdings, variant and cap checks
  output_columns.py  output entry lists
scripts/generate_ul_fund_slots.py
docs/products/unit-linked.md      user documentation (product, inputs, features, scenarios)
examples/demo/basis/...           new UL basis tables (generated by avk demo generate)
```

The family class `UnitLinkedProduct(Product)` is added to `avk.model.lang` with
abstract ports `premium_income`, `charge_income`, `acquisition_cost`,
`expense_outgo`, `non_unit_benefit_outgo`, `unit_reserve` and `coverage_units`.
Run-layer changes are limited to product-generic hooks (companion policy tables,
section 5.2) and must not change any existing output.

### 5.2 Inputs

Policy-level data lives in the policy table, fund-level data in the holdings table.
The tables share only key fields, and those must agree (validation, below).

**`policies_ul`** one row per policy (columns are explicit; none default):

| Group | Columns |
|---|---|
| Keys | Policy Number, Product Code, Product Variant, Valuation Date (must equal the run's valuation date) |
| Contract | Policy Start Date, Policy Term (Years), Premium Payment Term (Years; 0 for single premium), Premium Frequency (0 single, 1, 2, 4, 12), Annualised Premium (the single premium when single), Sum Assured, Distribution Channel, Currency |
| Life | Date of Birth, Age at Policy Start, Gender, Smoking Status, Underwriting Class, EMR (extra mortality multiple, 1 standard), Flat Extra (per mille a year), Flat Extra Term (Years) |
| Status | Policy Status (0 premium paying or fully paid, 1 discontinued in the DPF, 2 reduced paid-up), Status Date (date the current status began), Paid Up Sum Assured (status 2, else 0), Date Of Last Premium Paid |
| History to date (retrospective) | Premiums Paid To Date, Instalments Paid, Premium Allocation Charges To Date, Policy Administration Charges To Date, Mortality Charges To Date, Guarantee Charges To Date, Loyalty Additions To Date, Partial Withdrawals To Date, Withdrawals Current Policy Year, Withdrawals Previous Policy Year, Fund Value Sum Current Policy Year (sum of month-end fund values since the last anniversary), Discontinuance Charge Paid |
| IFRS 17 grouping | Portfolio, Issue Cohort (year), Profitability Group (0 onerous at recognition, 1 no significant possibility, 2 other), Transition Approach (0 full retrospective, 1 modified retrospective, 2 fair value), Measurement Model (VFA or GMM), Legal Entity |

**`policy_funds_ul`** one row per policy and fund held:

| Group | Columns |
|---|---|
| Keys | Policy Number, Product Code, Fund Code, Valuation Date |
| Holding | Units, Premium Allocation (fraction of future premiums; 0 for the DPF and closed funds), Fund Entry Date |
| History to date | Premiums Allocated To Fund, Units Allocated To Date, Units Cancelled To Date, Switches In To Date, Switches Out To Date |
| Guarantee state | Guaranteed Unit Price (highest NAV recorded, for guaranteed funds; else 0) |

Fund value = Units x unit price (unit price from `ul_funds`). A status-1 policy holds
exactly one row, in fund `DPF`; other policies hold none in `DPF`.

Validation (all before projection, exact error messages):

- every `policy_funds_ul` row's Policy Number exists in `policies_ul` and its
  Product Code and Valuation Date match the policy row; every policy has at least
  one holding row; Policy Number + Fund Code is unique;
- a policy holds at most `MAX_FUND_SLOTS` funds; every Fund Code exists in `ul_funds`;
  non-selectable funds (the DPF) carry zero allocation; allocations of a
  premium-paying policy sum to 1 within 1e-9; units are nonnegative;
- Product Variant exists in `ul_variants`; dates are consistent (start <= status date
  <= valuation date; age agrees with date of birth); history amounts are
  nonnegative; Premiums Paid To Date >= the sum of Premiums Allocated To Fund;
- when the variant's regime applies caps: every charge in the variant's scales and
  every selectable fund's FMC is within the regime's caps (section 5.8);
  Sum Assured >= the regime's minimum multiple of the premium for the entry age.

The run layer gains one product-generic hook: a factory may name companion policy
tables (`companion_tables = ("policy_funds_ul",)`); the run reads them once,
validates them, and gives them to the adapter, which joins them to each policy batch
(vectorised pivot into slot fields `Fund_k_*`). Existing products declare none.

**Fund-level assumption tables**

- `ul_funds` keyed by Fund Code: unit_price, fmc (annual), alpha (annual return
  over the asset mix, negative for tracking cost), w_<asset> for the ten asset
  classes (sum to 1), selectable, is_dpf, guarantee_type (0 none; codes reserved),
  risk_class (1 to 5).

**Product and regulation tables**

- `ul_variants` keyed by Product Variant: feature fields (section 5.7) and `regime`.
- `ul_charge_scales` by policy year and variant: premium_allocation_rate,
  admin_charge_monthly, loyalty_rate, booster_rate, disc_pct_low, disc_cap_low,
  disc_pct_high, disc_cap_high.
- `ul_regulatory_caps` by regime and field (section 5.8); `ul_disc_charge_caps` and
  `ul_riy_caps` by policy year and regime.

**Decrement, expense and economic tables**

- `mortality` (shared experience table) with product parameters for the experience
  percentage and smoker loading; `mortality_charges_ul` (guaranteed charge rates per
  1,000 by age and gender/smoker field).
- `lapse_rates_ul`, `partial_withdrawals_ul`, `commissions_ul` by year and channel.
- `interest_rates` (shared: roi, vroi, reference_forward) and `ul_asset_returns`
  (annual expected returns by year for the ten asset classes).
- `product_parameters`, column `UNIT_LINKED`: margins, expenses, tax, profit
  transfer (CSR), capital factors with and without guarantee, reserve floor days,
  revival strain percentages, surrender share, fund return margin, MC switch.

Field and format names above are the contract's intent; the P1 builder finalises
exact names and records them in `docs/products/unit-linked.md`.

### 5.3 Fund universe (invented demo, generic names)

Equity: `EQ_LARGE_CAP`, `EQ_INDEX` (passive, low FMC), `EQ_FLEXI_CAP`, `EQ_MID_CAP`,
`EQ_SMALL_CAP`, `EQ_VALUE`, `EQ_ESG`, `EQ_INFRA_THEME`, `EQ_GLOBAL`.
Hybrid: `HY_AGGRESSIVE`, `HY_BALANCED`, `HY_CONSERVATIVE`, `HY_DYNAMIC` (static mix
until dynamic allocation exists). Debt: `DT_GILT`, `DT_CORP_BOND`,
`DT_SHORT_DURATION`, `MM_LIQUID`. Alternatives: `ALT_GOLD`, `ALT_REAL_ASSETS`.
Guaranteed: `GT_HIGHEST_NAV`, `GT_CAPITAL_PROTECT` (static mixes; guarantee
mechanics are a later phase). System: `DPF` (not selectable). FMCs sit within the
1.35% cap (DPF 0.50%).

### 5.4 Market variables (scenario variables)

`roi`, `vroi`, `reference_forward` (from `interest_rates`, as Term) and ten monthly
asset-class total returns from `ul_asset_returns`: `ret_eq_large`, `ret_eq_mid`,
`ret_eq_small`, `ret_eq_global`, `ret_gov_long`, `ret_gov_short`, `ret_corp_bond`,
`ret_money_market`, `ret_gold`, `ret_real_assets`. Deterministic runs derive them
with `DeterministicCurveESG` (monthly effective, `lag`, 1 month). A supplied Parquet
scenario set carries exactly these columns and runs every path in one kernel call.

Fund k gross monthly return on basis b:

- be: `g_k = sum_j w_kj r_j[t] + alpha_k_monthly`
- reserving: be plus the signed monthly fund return margin
- mc: `reference_forward[t]` for every fund when `mc_fund_return_source = 0`
  (certainty equivalent); the be formula when it is 1 (use with risk-neutral sets).

### 5.5 Policy states and decrements

States: active (A), discontinued in the DPF (D), reduced paid-up (R). At t = 0 a
policy is wholly in the state given by Policy Status. Monthly order (from the
opening lives of each state): deaths, then surrenders (any month), then premium
cessation (premium due months within the premium term, frequency exponent), then
maturity in the term's last month. The annual discontinuance rate splits into
surrender and cessation by `surrender_share`. Inside the lock-in both go to D;
after it a surrender pays out and a cessation goes to R (or pays out, by
`rpu_mode`). R lives die, surrender, mature and (rpu_mode 2) leave at the end of the
revival period. D lives die or are paid at the end of the lock-in. Experience
mortality and the reserving margins apply on all states; the mortality charge table
is contractual (no margin).

### 5.6 Unit fund roll per active life (order of operations, month m)

1. `F0_k` opening value (input at t = 0, else last month's close); at an anniversary
   with `auto_rebalance` on, `F0_k = F0 x a_k`.
2. Premium `P` when due; `PAC = P x premium_allocation_rate(py)`;
   `F1_k = F0_k + (P - PAC) x a_k`; premiums paid accumulate (`TPP`).
3. Partial withdrawal `PW = F1 x pw_rate` (when allowed, from its start year).
4. Admin charge `ADM` (scale, escalated) and guarantee charge `GC = F1 x gc_monthly`.
   `F3 = F1 - PW - ADM - GC`.
5. Effective sum assured `SA_eff = SA - withdrawals of the current and previous
   policy year` when `pw_reduces_sa`, else `SA`. Type I:
   `SAR = max(max(SA_eff, m x TPP) - F3, 0)`; Type II: `SAR = max(SA_eff, m x TPP - F3)`.
   `MC = SAR x charge rate(age) x EMR / 1000 / 12 + SAR x flat extra / 1000 / 12`.
   Deductions `PW + ADM + GC + MC` are taken from the slots in proportion to `F1_k`,
   never more than the fund.
6. Additions at the end of a policy year when the feature is on and its conditions
   hold: loyalty (`loyalty_rate(py)` x average month-end fund value of the year, or x
   AP by `loyalty_basis`), booster, guaranteed additions; allocated in proportion
   to the fund.
7. Growth `F5_k = (F4_k + LA_k) x (1 + g_k)`.
8. `FMC_k = F5_k x (1 - (1 - fmc_k)^(1/12))`; close `F_k = F5_k - FMC_k`.

Exits are paid at the end of the month on the closing fund `F = sum_k F_k`:
death benefit Type I `max(SA_eff, F, m x TPP)`, Type II `max(SA_eff + F, m x TPP)`;
the units pay `F`, the general fund the rest. (Orchestrator's call: the model spec
measures the general fund's death cost at `F3`; measuring the payment on the closing
fund keeps the unit segment reconciling exactly. The mortality charge still uses
the sum at risk at `F3`, as the contract states.) Surrender pays `F` less the
discontinuance charge inside the lock-in (to the DPF) or `F` after it. Maturity
pays `F` plus general-fund top-ups: the maturity guarantee
`max(gmmb_multiple x TPP - F, 0)` and returned charges (fractions of cumulative
mortality, allocation and admin charges).

### 5.7 Design features (fields of `ul_variants`)

| Feature | Fields |
|---|---|
| Death benefit | death_benefit_type (1 Type I, 2 Type II), min_db_premium_multiple |
| Premium type | single_premium (0/1); limited pay is PPT < term |
| Lock-in and DPF | lock_in_months, dpf_enabled |
| Paid-up | rpu_mode (0 cessation pays out, 1 paid-up to maturity, 2 paid-up with revival-period expiry), revival_period_months |
| Partial withdrawals | pw_allowed, pw_start_year, pw_reduces_sa |
| Loyalty and boosters | loyalty_on, loyalty_basis (1 average fund, 2 annualised premium), loyalty_start_year, loyalty_requires_full_premiums, guaranteed_addition_rate |
| Return of charges | romc_fraction, ropac_fraction, roadmin_fraction (paid at maturity) |
| Maturity guarantee | gmmb_on, gmmb_premium_multiple, guarantee_charge (annual, by unit cancellation) |
| Charges | admin_escalation, mortality_charge_multiplier, disc_ap_threshold |
| Funds | auto_rebalance |
| Regulation | regime (caps applied when not UNCAPPED), riy_additions_on (read from P3) |

### 5.8 Regulatory caps

`ul_regulatory_caps` (IRDAI_2024 values from the source specification; UNCAPPED has
no limits): premium allocation charge maximum and first-five-year max/min ratio,
admin charge maximum per month and escalation maximum, FMC maximum, DPF FMC maximum,
guarantee charge maximum, minimum death benefit multiple of premiums, minimum lock-in,
DPF minimum guaranteed rate, minimum sum assured multiples by entry-age band and
premium type, switching/withdrawal/miscellaneous charge maxima. Validation rejects a
variant whose charges breach its regime's caps (orchestrator's call: reject, never
clamp silently). The DPF guaranteed rate and FMC come from the regime.

### 5.9 DPF and reduced paid-up funds

Both are aggregate expected funds per policy (single-cohort simplification, stated in
the documentation). DPF: inflows are discontinuances at `F` less the discontinuance
charge; monthly credit `max(actual DPF return, guaranteed rate)` less the DPF FMC
(spec 7.3); shareholders bear the guarantee shortfall; proceeds are paid on death or
at the end of the lock-in. RPU: per-slot aggregate funds, aggregate paid-up sum
assured `SA x instalments paid / instalments payable`, aggregate premiums paid;
admin, mortality (on the aggregate paid-up sum at risk), FMC and guarantee charges
continue; no loyalty additions; mode 2 leaves at `1/revival_period_months` a month.

### 5.10 General fund (non-unit) cashflows, per basis

Income: allocation charges, admin, mortality, guarantee, fund management (A, R, D)
and discontinuance charges. Outgo: commission, initial and renewal expenses (renewal
inflated from the valuation date), fund expenses (% of unit funds), claim expenses,
death benefit above the units, maturity guarantee top-ups, returned charges, loyalty,
booster and guaranteed additions, residual additions (0 until P3), DPF guarantee cost.
`net_cashflows` is outgo less income plus interest (positive when the reserve pays
out), as elsewhere; start-of-month items earn a month's interest.

### 5.11 Reserves, profit, capital, MCEV

- Unit reserve: A fund x A lives + R funds + D fund.
- General fund reserve: backward recursion of `net_cashflows` at the basis rate
  (vroi reserving, roi be); held value `max(DCF, 0, floor_days/365 x annual
  mortality charge)`; revival strain provisions on D and R funds; total reserve.
- Best-estimate profit signature: non-unit cashflow (income positive) less the
  increase in the held general fund reserve plus interest; profit transfer (CSR) and
  tax; unit segment profit must be nil (check).
- Solvency: `factor1 x (unit + general fund reserve) + factor2 x sum at risk`, with
  factors with or without guarantee by variant, times the target ratio; cost of
  capital.
- MCEV (mc basis): profit chain at the reference forward rate with funds growing at
  it; PVFP, frictional cost, cost of residual non-hedgeable risk, VIF.

### 5.12 Outputs

Aggregate entries by basis layer (`_reserving`, `_BE`, `_MC`): lives and exits by
state, premiums, allocated premium, every charge, unit funds by state, benefits split
unit/general fund, general fund cashflows, reserves and floors, profit chain,
capital, MCEV values. Seriatim at step 0: unit reserve, held general fund reserve,
total reserve, BEL, PVFP, VIF, sum at risk, annualised premium. Detailed policy-month
output uses the existing flag.

### 5.13 Stochastic readiness

- Every market quantity is a scenario variable; one compiled kernel serves the
  deterministic path, real-world sets (distributions) and risk-neutral sets
  (`mc_fund_return_source = 1`, path-wise discounting at `reference_forward`).
- Path-dependent features (DPF floor, maturity guarantee, later highest NAV and
  dynamic lapse) are computed per path by construction.
- Later (P4): a multi-asset generator (correlated lognormal asset classes, seeded,
  real-world and risk-neutral), `avk scenarios` tooling that writes the supplied
  Parquet format, a deterministic scenario library (illustration 4%/8%, equity fall,
  sustained low return), and scenario summaries (weighted mean, percentiles, CTE,
  TVOG = risk-neutral mean less the certainty equivalent).

## 6. Verification

- The model specification's checks: decrements exhaustive across states; unit fund
  reconciliation every month; charge outgo equals charge income; sum at risk never
  negative and nil above the floors; no mortality charge without sum at risk;
  recursion equals discounted summation; floors hold; reserve roll-forward ties;
  reserving reserve at least the BEL (reported per case); DPF never below the
  guaranteed rate; fund nil after maturity; unit segment profit nil; mc funds grow
  at the risk-free rate.
- An independent scalar Python oracle (four policies, every basis, every month)
  reconciled column by column with `avk.testing.parity`.
- Batch and thread invariance, NUMBA_DISABLE_JIT guard, existing saved tables
  byte-identical, project checks in CLAUDE.md.

## 7. Phases

| Phase | Scope | Worker |
|---|---|---|
| P0 | Design, tracker, phase prompts, integration branch | Orchestrator |
| P1 | Inputs and contracts: formats, companion holdings table, adapter and slot fields, validation and caps, fund universe and demo inputs, factory and skeleton product | Claude session (Opus 5.5, medium) |
| P4a | Scenario tooling (parallel with P1): multi-asset generator, settings in the generator registry, `avk scenarios` writer, deterministic scenario library | Codex `gpt-6.2-sol` |
| P2a | Unit engine: slot generator, states and decrements, unit roll, charges, DPF, RPU, benefits and features | Codex `gpt-6.2-sol` |
| P2b | General fund, reserves, profit, capital, MCEV, outputs, oracle, checks, saved results, docs | Claude session (Opus 5.5, medium) |
| P3 | Reduction in yield and residual additions, compliance demonstration, benefit illustration | Claude session (Sonnet 5.5, high) |
| P4b | Stochastic results: summaries, TVOG, dynamic lapse, tutorial | Codex `gpt-6.2-sol` |
| P5 | IFRS 17 VFA measurement and stress-capital support for UL | Claude session (Opus 5.5, medium) |
| P6 | Feature extensions (lifecycle/STP, top-ups, premium funding, highest NAV, settlement, pension, GST) | Split when reached |

## 8. Orchestration and resilience

- Integration branch `feature/unit-linked`; each phase on `ul/<phase>-<slug>` in its
  own worktree under `C:\avkwt\` (short paths, outside OneDrive).
- Workers commit work-in-progress locally on their branch at every green step, keep
  `docs/superpowers/plans/ul-<phase>-log.md` current (done, decisions, next step),
  never push and never touch `main` or `feature/unit-linked`.
- The orchestrator reviews each diff, runs the checks, merges into
  `feature/unit-linked`, pushes, and updates the tracker. A pull request to `main`
  follows when the first delivery (P1, P2a, P2b) is complete.
- A worker stopped by a usage limit is resumed (same worker or another) with its
  phase prompt plus "resume from the log and the last commit".

## 9. Calls made by the orchestrator

1. Product code `UNIT_LINKED`; regime default `IRDAI_2024`, plus `UNCAPPED`.
2. `MAX_FUND_SLOTS = 5` (a generator constant).
3. A third `mc` basis rather than reusing the protection MCEV component.
4. Exits paid on the closing fund (section 5.6).
5. DPF and RPU as aggregate funds per policy; RPU expiry as an exponential exit.
6. Caps validated and rejected, not clamped.
7. CSV/Parquet inputs, one file per logical table.
8. Withdrawal-reduced sum assured uses the current and previous policy year.
9. Loyalty average uses month-end values over the policy year.
10. No GST and no reinsurance in the first delivery.

## 10. Left to builders

Exact column, field, format and output names; demo calibration within the stated
ranges; compile-time and performance tuning; which shared components are reused
(reuse only where the semantics match exactly).
