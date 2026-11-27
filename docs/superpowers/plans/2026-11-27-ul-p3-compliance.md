# UL P3: compliance layer — implementation plan

> **For agentic workers:** implement this plan task by task, test first, inline (no
> sub-agents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The regulatory compliance layer of UNIT_LINKED: the reduction in yield (RIY) of a
policy or variant against `ul_riy_caps`, the residual addition that would restore a breached
cap, the pricing-time compliance demonstration for every variant at 4% and 8% gross, and the
benefit illustration by policy year. Public API functions, two CLI commands, CSV outputs and
documentation. Wiring residual additions into the general fund and the units is a later step
(after P2b merges) and is only prepared here.

**Architecture:** A pure numeric module `src/avk/products/unit_linked/illustration.py`
projects one life under a fixed gross return (the P2a fund roll of design 5.6 without
decrements, withdrawals or lifecycle) and solves net yield, RIY and residual additions. It
reads no files and no tables: it takes a `Case` (the prepared model-point contract plus
per-year charge arrays). An orchestration module `src/avk/runs/ul_compliance.py` runs the
normal input gate (`check`), builds cases from the prepared book or from the variant, fund
and charge tables, applies the library's flat scenario for the gross rates, calls the
projection and writes CSV through `CsvSink`. `avk.api` exposes two functions, `avk.cli` two
commands. No existing module changes except those entry points, `docs`, and `CHANGELOG`.

**Tech stack:** Python 3.13, numpy, polars, pytest, uv. No formula module is added, so the
import-linter formula contract and the mypy formula override do not change.

**Spec:** `docs/superpowers/specs/2026-11-26-unit-linked-product-design.md` sections 5.7
(`riy_additions_on`), 5.8, 5.13 and 7 (P3). Source material: the maintainer's product and
model specifications (read-only, private; never copy or quote their text).

## Global constraints

- Every project check in `CLAUDE.md` passes; existing saved results stay byte-identical;
  tolerances are never relaxed. Unit-engine results do not change.
- Do not create or edit general-fund, reserve, profit, capital or MCEV modules, the
  valuation entries of `UnitLinkedFactory.output_schema`, `src/avk/testing/demo.py` or
  `tests/saved` (P2b owns them in parallel).
- Parity comparisons use `avk.testing.parity` classes: money 1e-6 relative plus 1e-8 times
  scale, rates 1e-12 relative. The independent IRR in tests is solved by a different method
  from the code under test (closed form or polynomial roots).
- The illustration reproduces the engine's per-life roll exactly (the engine columns are
  per active life, so they are the no-decrement path). A reconciliation test ties the two.
- Write in own words; never copy or quote the private specifications into the repository.
- Commit after every green task; keep `docs/superpowers/plans/ul-p3-log.md` current.
- Windows under OneDrive: `UV_LINK_MODE=copy` for every uv command.

## Review focus

1. The RIY run excludes mortality charges (with EMR and flat-extra loadings), the guarantee
   charge, partial withdrawals, decrements and tax on charges, as the product specification
   states; the illustration run keeps every charge. Test in Task 1.
2. Net yield is an annual-effective IRR with each instalment at the start of its policy
   month and the fund value at the end of policy month 12n. Test in Task 1 against closed
   form (single premium) and polynomial roots (regular premium).
3. The residual addition is never negative, is zero when the cap holds, is zero before the
   first permitted anniversary, and, once credited, brings the measured net yield to exactly
   `gross - cap`. Later years see the augmented fund. Test in Task 2.
4. A breach before the first permitted addition year is a design failure, never repaired by
   additions; a variant with `riy_additions_on = 0` cannot rely on additions. Test in Task 2.
5. The illustration's fund values equal the engine's `fund_close_total` per life at 4% and
   8% for variants exercising loyalty, boosters, rebalancing, escalation, guarantee charge
   and fund exhaustion. Test in Task 1.

---

## Notation

`g` annual-effective gross return, `g_m = (1 + g)^(1/12) - 1`; month `m = 1..M`,
`M = 12 x term`; year `n = ceil(m / 12)`. Per fund slot `k`: `a_k` normalised allocation,
`f_k` annual FMC. Premium `P` at the start of month `m` when due (design 5.5/P2a rules).
Net yield `y_n` solves `sum_j P_j (1 + y)^(n - (m_j - 1)/12) = F_n` where `F_n` is the
fund value at the end of month `12n`. `RIY_n = g - y_n`. Cap `c_n = riy_max[n, regime]`.
Target `y*_n = g - c_n`, `F*_n = sum_j P_j (1 + y*_n)^(n - (m_j - 1)/12)`,
`addition_n = max(F*_n - F_n, 0)`, credited at the end of month `12n` pro rata to the slots.
Constants: `FIRST_MEASUREMENT_YEAR = 5`, `FIRST_ADDITION_YEAR = 6`.

## Components

### `illustration.py` (pure; numpy only)

- `ChargeSchedule`: per policy year arrays (index `year - 1`, last value repeats):
  `pac_rate`, `admin`, `loyalty_rate`, `booster_rate`, `disc_pct_low/high`,
  `disc_cap_low/high`, `riy_cap`; mortality charge per mille by age (`age -> float`).
- `Case`: contract fields (term, payment term, frequency, single, instalment, annualised
  premium, sum assured, entry age, EMR, flat extra, flat-extra term), variant features
  (the `V_*` contract of `fields.VARIANT_FEATURES` without the prefix), fund slots
  (allocation, FMC), the schedule and `riy_additions_on`.
- `project(case, gross, *, risk_charges, additions=False)` returns a `Path` of monthly
  arrays and year-end values: premium, each charge, additions by kind, fund by month, total
  premiums, death benefit, surrender value, maturity value; with `additions=True` residual
  additions are solved sequentially at each permitted anniversary.
- `net_yield(times, premiums, value, years)`: bracketed bisection with a final Newton
  polish; `riy(path)`: yearly net yield, RIY, cap, excess, pass flag.

### `ul_compliance.py` (orchestration)

- `ul_compliance(run_file, *, rates=(0.04, 0.08), terms=(10, 20, 30), frequencies=(1, 12),
  premiums=None, fund=None, output=None)`: the pricing-time demonstration; one row per
  variant, case, rate and policy year plus a summary per variant and rate.
- `ul_illustration(run_file, policy, *, rates=(0.04, 0.08), output=None)`: the benefit
  illustration of one policy as sold (premium-paying status 0 policies), per rate and year.
- Gross scenarios use `avk.esg.library.flat` on a ten-variable one-step scenario set; the
  monthly return must be identical across the asset classes.

### Outputs (CSV via `CsvSink`; no xlsx writer or dependency exists in the repository)

- `ul_riy_cases.csv` and `ul_riy_summary.csv` (demonstration).
- `ul_illustration_<policy>.csv` (benefit illustration; columns documented in the docs).

---

### Task 1: Single-life projection, net yield and RIY

**Files:** create `src/avk/products/unit_linked/illustration.py`, `tests/unit_linked/test_illustration.py`.

- [ ] Tests (written first): (a) hand-computed single premium: premium 100,000, allocation
  rate 5%, admin 0, one fund FMC 1.35%, gross 8%, 10 years, risk charges off: fund after
  `n` years is `95,000 x ((1.08)^(1/12) x (1 - 0.0135)^(1/12))^(12n)`; the net yield solved
  independently in the test (closed form `(F/P)^(1/n) - 1`) equals `net_yield` to 1e-12;
  RIY equals `g - y`. (b) hand-computed regular premium (annual, 5 instalments, admin
  charge, two funds): the independent test solves the IRR polynomial with `numpy.roots`
  and compares to 1e-10. (c) risk charges off: the fund path ignores EMR, flat extra and the
  guarantee charge; risk charges on: equals the engine roll (d). (d) Reconciliation with the
  engine: for ULIP_CLASSIC annual, ULIP_WEALTH_T2 monthly, ULIP_LIMITED_PAY_ROC (rebalance,
  escalation, quarterly) and ULIP_MATURITY_GUARANTEE (guarantee charge) at 4% and 8%, with
  `ul_projection` rows set to inception (`Duration_in_Months = 0`, no history, zero holdings,
  `V_pw_allowed = 0`, `Fund_k_Alpha = 0`): every month `fund_close_total`, `pac_pp`,
  `admin_pp`, `mc_pp`, `gc_pp`, `fund_1_fmc` per life agree to 1e-9 relative, and the year-end
  death benefit and maturity value (fund plus return of charges plus guarantee top-up)
  agree with the benefit formulas. (e) Fund exhaustion (tiny premium, huge admin): charges
  scale down and the fund never goes negative. (f) The gross rate scenario obtained from
  `avk.esg.library.flat` equals `(1 + g)^(1/12) - 1`.
- [ ] Implement; `uv run pytest tests/unit_linked/test_illustration.py`. Commit; log.

### Task 2: Cap test and residual additions

**Files:** `illustration.py`, `tests/unit_linked/test_residual_additions.py`.

- [ ] Tests: the cap lookup by regime and year (including repeats beyond the table); a
  compliant design gives zero additions at every year; a breaching design (large admin
  charge) gives positive additions only from the sixth anniversary and, once credited, the
  measured net yield equals `g - cap` to 1e-12 (single premium, hand: `F* = P (1 + y*)^n`);
  later-year additions see the augmented fund (sequential: the year-7 addition is smaller than
  the stand-alone shortfall); a breach at year 5 is `design_fail`; `riy_additions_on = 0`
  with a breach after year 5 is `fail` with the shortfall reported but no addition credited;
  the regime `UNCAPPED` (cap 1.0) never breaches; additions never negative.
- [ ] Implement `riy`, `solve_additions`, the status rule: `pass` (no breach),
  `pass_with_additions` (breaches only from the first addition year and additions are on),
  `fail` otherwise. Commit; log.

### Task 3: Compliance demonstration, API and CLI

**Files:** create `src/avk/runs/ul_compliance.py`; modify `src/avk/api.py`, `src/avk/cli.py`;
tests `tests/unit_linked/test_compliance_run.py`.

- [ ] Tests: on the 6-policy demo book the demonstration returns rows for every variant in
  `ul_variants`, both rates, every case and year; summary has one row per variant, case and
  rate with status; `UL_INVESTMENT_BOND` (UNCAPPED) passes; the output CSV files exist and
  read back; the cases are deterministic (two runs equal); `avk ul compliance run.json
  --output folder` exits 0 and prints the summary; an unknown policy or non-UNIT_LINKED run
  gives `avk: ... Error` and exit 1; the check gate is the normal one (an invalid book is
  rejected with the usual error).
- [ ] Implement. Add `ul_compliance` to `avk.api`. Commit; log.

### Task 4: Benefit illustration, API and CLI

**Files:** `src/avk/runs/ul_compliance.py`, `src/avk/api.py`, `src/avk/cli.py`; tests
`tests/unit_linked/test_illustration_output.py`.

- [ ] Tests: columns and order (policy, rate, year, premiums, each charge, additions, fund
  value, death benefit, surrender value, maturity value, net yield, RIY, cap); year-end values
  equal the Task 1 projection; the maturity value in the final year is the maturity benefit;
  inside the lock-in the surrender value is the fund less the discontinuance charge and the
  payable month is the lock-in end when the DPF is on; a status 1 or 2 policy is rejected
  with a clear message; `avk ul illustration` writes the CSV for 4% and 8%.
- [ ] Implement. Commit; log.

### Task 5: Documentation, CHANGELOG and checks

**Files:** `docs/products/unit-linked-compliance.md` (new), `docs/products/unit-linked.md`
(link and status line), `docs/how-tos.md` if it lists commands, `CHANGELOG.md`, generated
reference pages if the CLI help is part of them, `docs/superpowers/plans/ul-p3-log.md`.

- [ ] Docs: method (definitions, timing, exclusions, measurement years), the two commands,
  output columns, status rules, limitations, residual-addition wiring status.
- [ ] Run every project check in `CLAUDE.md` (except `uv sync`) and `pytest -m slow`; record
  results and the final report in the log.

## Done when

All tasks pass, every project check passes, the hand-computed single-premium and
regular-premium RIY tests pass with independently solved IRRs, and `ul-p3-log.md` records
the decisions and the open point (general-fund and unit wiring of residual additions).
