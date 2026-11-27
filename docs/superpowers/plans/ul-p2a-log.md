# UNIT_LINKED P2a implementation log

Branch `ul/p2a-unit-engine`. Work is in the working tree for orchestrator review.

## Task 1 — Family ports and slot generator

- Files `src/avk/model/lang.py`, `pyproject.toml`, `scripts/generate_ul_fund_slots.py`, `src/avk/products/unit_linked/{formulas,fund_slots}.py` and `tests/unit_linked/test_fund_slots_generated.py`.
- `uv run --no-sync pytest tests/unit_linked/test_fund_slots_generated.py -q` passed 2 tests (2 failed before implementation). `uv run --no-sync avk compile UNIT_LINKED` compiled 11 columns in one pass.
- The generator reads the catalogue directly and uses Ruff on stdin. Its slot count backs the formula field contract as well as the generated columns. P1 opening-fund outputs remain available.
- Next is Task 2, rates and lives.

## Task 2 — Rates and lives

- Files `src/avk/products/unit_linked/{decrements,lives,formulas}.py`, `pyproject.toml`, `tests/unit_linked/{conftest,test_decrements}.py`.
- `uv run --no-sync pytest tests/unit_linked/test_decrements.py -q` passed 15 tests (the first test failed before implementation because the rate columns were absent). `uv run --no-sync avk compile UNIT_LINKED` compiled 114 columns in one pass.
- Used the same shock parameters as Term and guarded DPF lock-in payout with projection step > 0. Used the exact positive paid-up opening lives denominator in the lazy branch, preserving fund and payout shares even for very small cohorts.
- The plan's cessation equation can enter paid-up at maturity for monthly pay, which strands the new cohort beyond the term and conflicts with Task 7. The maturity month therefore excludes ordinary surrender and cessation while retaining the last scheduled premium and maturity benefit. Ordinary surrenders are enabled in the preceding months of the final year, following the plan's explicit month indicator.
- Next is Task 3, premiums and the active fund.

## Task 3 — Premiums and the active unit fund

- Files `src/avk/products/unit_linked/{formulas,premiums,fund_slots}.py`, `scripts/generate_ul_fund_slots.py`, `pyproject.toml`, `tests/unit_linked/{conftest,test_unit_fund}.py`.
- `uv run --no-sync pytest tests/unit_linked/test_unit_fund.py tests/unit_linked/test_fund_slots_generated.py -q` passed 7 tests. The scalar roll failed first on the missing premium column.
- Rebalancing precedes the first instalment of the new policy year, uses normalized allocation weights and leaves the existing mix alone if there are no weights. Two-year cover reduction uses carried withdrawals before the current month's deduction and drops the older year at rollover. The latest charge amount is therefore available for cover in the next month. Retained fund value is floored at zero by the exhaustion branch, including when all requested amounts exactly consume the fund.
- Next is Task 4, the exhaustion and additions tests.

## Task 4 — Charges, exhaustion and additions

- Files `src/avk/products/unit_linked/{formulas,premiums,fund_slots}.py`, `scripts/generate_ul_fund_slots.py`, `tests/unit_linked/{test_charges,test_unit_fund}.py`.
- `uv run --no-sync pytest tests/unit_linked/test_charges.py tests/unit_linked/test_unit_fund.py tests/unit_linked/test_fund_slots_generated.py -q --tb=short` passed 15 tests. Before implementation the three deduction tests passed and the first loyalty test failed on the missing column.
- Eligibility compares the cumulative paid instalments with the schedule through the anniversary, capped by contractual instalments payable. The anniversary average uses the eleven carried month-end balances and the current pre-addition, post-deduction balance, as the plan specifies. Step 0 carries the supplied year-to-date balance exactly.
- A fully paid policy can exhaust its funds and have zero allocation weights. The first pass credited no addition in this combination. The orchestrator confirmed the convention in the 2026-11-27 review.
- Next is Task 5, the DPF.

## Task 5 — Discontinued Policy Fund and discontinuance charges

- Files `src/avk/products/unit_linked/{dpf,formulas}.py`, `pyproject.toml`, `tests/unit_linked/test_dpf.py`.
- `uv run --no-sync pytest tests/unit_linked/test_dpf.py -q --tb=short` passed 9 tests. The first charge test failed on the missing column before implementation.
- Credit the opening balance before exits, apply the FMC to the credited balance and transfer new entrants net of charge. A transfer in the boundary month is paid in the same month without an additional month's return. An overdue holding pays at step 1.
- P1 checked the DPF FMC only on opening DPF holdings. The DPF can now receive transfers, so preflight also checks it for capped, DPF-enabled variants with a positive lock-in. This was verified in Task 7 using the validation regression.
- Next is Task 6, reduced paid-up funds.

## Task 6 — Reduced paid-up funds

- Files `src/avk/products/unit_linked/{paid_up,formulas,fund_slots}.py`, `scripts/generate_ul_fund_slots.py`, `pyproject.toml`, `tests/unit_linked/test_paid_up.py`.
- `uv run --no-sync pytest tests/unit_linked/test_paid_up.py -q --tb=short` passed 5 tests. The first test failed on missing paid-up premium history before implementation.
- Opening paid-up holdings receive their own slot returns and charges. Cessations add at closing using the active slot mix, paid instalments and premium history. Opening paid-up cohorts take no new premiums, withdrawals or additions.
- Next is Task 7, benefits, ports, outputs and unit reconciliation.

## Task 7 — Benefits, ports, outputs and reconciliation

- Added the unit/general fund benefit split, the family ports, aggregate entries on all three bases and the generated schema reference. The first benefit test failed before implementation on the missing unit death column.
- P1 accepts a policy at `Duration_in_Months == Policy_Term * 12`, but the P2a plan schedules maturity only in that policy month and prohibits step-0 cashflows. The 10,000-policy seed-209 demo contains 32 active and 2 paid-up records at that boundary. Starting balances are present at step 0. With the literal timing formula no maturity can be scheduled for these policies. The orchestrator settled the timing convention in the 2026-11-27 review.
- In the first pass a lock-in extending past the insurance term deferred the DPF payout even though growth and mortality ended at term end. The 2026-11-27 review set the release date.

- The DPF FMC preflight regression failed before the cap check for projected transfers. `uv run --no-sync pytest tests/unit_linked/test_validation.py tests/unit_linked/test_unit_segment.py -q --tb=short` passed 70 tests after the cap check and a test-fixture correction for MC parameter overrides.
- The first 10,000-policy valuation (seed 209, 372 months, three bases, one scenario) completed with 655 columns in one forward pass, cold compile 71.22 s, cached load 0.97 s, projection 2.43 s and CLI elapsed 8.46 s. The phase records the maturity boundary separately from these performance measurements.

### Final verification

| Check | Result |
|---|---|
| `uv run --no-sync ruff check .` | Pass |
| `uv run --no-sync ruff format --check .` | Pass, 223 files |
| `uv run --no-sync mypy` | Pass, 135 source files |
| `uv run --no-sync lint-imports` | Pass, 14 contracts kept, 0 broken |
| `uv run --no-sync python scripts/generate_reference.py --check` | Pass, reference current |
| `uv run --no-sync python scripts/generate_ul_fund_slots.py --check` | Pass, generated source current |
| `uv run --no-sync python scripts/check_clean_install.py` | Pass, isolated runtime wheel and TERM valuation |
| `uv build` | Pass, sdist and wheel. uv warned that its configured cache directory is under the source directory. |
| `uv run --no-sync pytest` | Pass, 411 tests, 8 deselected, 38m 10s |
| `uv run --no-sync pytest -m slow` | Pass, 6 tests, 374 deselected, 50m 34s |
| Focused `NUMBA_DISABLE_JIT=1` pytest | Pass, 48 tests across decrements, charges, DPF, paid-up, benefits and reconciliation |

The 10,000-policy aggregate and seriatim CSVs matched byte-for-byte at batch size 1024
with one Numba thread and batch size 8192 with four threads. The CLI benchmark
record and temporary diagnostic data are in `.tmp/p2a-10k`.

The maturity boundary diagnostics confirmed zero payouts for all 34 affected policies.
The 32 active records lose INR 160,778,430.77 of opening unit reserve at the next
step with no attributable outgo. The two paid-up records retain INR 4,703,804.70
through the last step. These two effects share the same unscheduled maturity.

### Task 7 targeted results and handoff

- Files `src/avk/products/unit_linked/{benefits,factory,formulas,fund_slots,output_columns,validation}.py`, `scripts/generate_ul_fund_slots.py`, `pyproject.toml`, `tests/unit_linked/{conftest,test_benefits,test_unit_segment,test_skeleton_run,test_validation}.py`, `docs/products/unit-linked.md`, `docs/reference/output-columns.md`.
- `uv run --no-sync pytest tests/unit_linked/test_benefits.py tests/unit_linked/test_unit_segment.py -q` passed 11. `uv run --no-sync pytest tests/unit_linked -q --tb=short` passed 191.
- Active and paid-up death benefits use the closing fund before exits. Active maturity credits the return of charges toward the guarantee floor and pays the remainder as a top-up. The unit-exit total is also available separately from partial withdrawals for reconciliation.
- The P2b bridge is `premium_income`, `charge_income`, `non_unit_benefit_outgo` and `unit_reserve`. The non-unit benefit port includes additions and the DPF guarantee cost. P2b owns expenses, commissions, the general-fund reserve and floors, profit, capital, MCEV, the extended family ports, final schema and the oracle and saved results.
- The 2026-11-27 review resolved valuation-month maturity, long lock-in and additions with no allocation destination.

The slow suite started early because its selection contains only the existing products' 100,000-policy regressions. Its deselection count reflects that collection.

All requested checks completed. The default and slow regressions passed against the approved references. The tracked `tests/saved` tree is byte-identical to HEAD. All changes are in the working tree for orchestrator review.

## Orchestrator review decisions of 2026-11-27

### Decision 3 — Anniversary additions with no destination

- Files `tests/unit_linked/test_charges.py`. The existing formulas already zero both the unit credit and `addition_outgo` when a fully paid policy exhausts its units and has no allocation weights. The test verifies the per-slot credit and the general-fund benefit total on all three bases.
- `uv run --no-sync pytest tests/unit_linked/test_charges.py -k without_a_destination -q --tb=short` passed 1 test.
- Next is to verify valuation-month maturity and term-end DPF release.

### Decision 1 — Valuation-month maturity

- Files `src/avk/products/unit_linked/{decrements,dpf,fund_slots}.py`, `scripts/generate_ul_fund_slots.py`, `tests/unit_linked/test_benefits.py` and `docs/products/unit-linked.md`.
- Before the fix, the active and paid-up cases failed because each reported zero maturity lives at step 1. The overdue DPF case already passed. With `NUMBA_DISABLE_JIT=1`, `uv run --no-sync pytest tests/unit_linked/test_benefits.py -k matured_at_valuation -q --tb=short` passed all 3 cases. The staged JIT run, `uv run --no-sync pytest -q tests/unit_linked/test_benefits.py tests/unit_linked/test_paid_up.py tests/unit_linked/test_decrements.py tests/unit_linked/test_fund_slots_generated.py --tb=short`, passed 32 tests.
- The new maturity indicator settles these policies from the carried balances at step 1. The existing live mask still controls premiums, charges, returns, decrements, rebalancing and additions. Paid-up and DPF openings already carry their previous close. The charge refund and maturity guarantees use the existing benefit formulas.
- Next is to cap the DPF release date at term end and compare ordinary-policy diagnostics with the first pass.

### Decision 2 — DPF release at lock-in end or term end

- Files `src/avk/products/unit_linked/{decrements,dpf,lives}.py`, `tests/unit_linked/test_dpf.py` and `docs/products/unit-linked.md`.
- Before the fix the surviving DPF balance had no payout in the final term month when lock-in ran for another year. With `NUMBA_DISABLE_JIT=1`, `uv run --no-sync pytest tests/unit_linked/test_dpf.py -q --tb=short` passed 10 tests.
- The release indicator now uses the earlier date for the balance and lives. Overdue holdings still pay at step 1.
- Next is the seed-209 demo and final project checks.

### Seed-209 demo and ordinary-policy comparison

- Files `tests/unit_linked/test_unit_segment.py`. The 10,000-policy regression
  streams bounded batches and applies the repository's money parity rule per policy.
  It checks the opening reserve, monthly unit roll and zero reserve and lives from
  the maturity settlement step on `reserving`, `be` and `mc`.
- The demo test failed before implementation on lives remaining after maturity.
  `uv run --no-sync pytest tests/unit_linked/test_unit_segment.py -m slow -q --tb=short --durations=1`
  passed 1 test, with 4 deselected, in 179.41 s including a cold kernel build.
  This runtime warrants the `slow` marker.
- `uv run --no-sync python .tmp/p2a-review-control.py` compared the first pass
  and final formulas on 43 ordinary demo policies across all statuses, including
  step-1 maturities, a mass-lapse case and only lock-ins ending within the term.
  All 655 original diagnostic columns matched byte-for-byte across 372 steps.
  The before and after SHA-256 was
  `9f4b041b90d3b18c818a0c3d50f90b36d42e9bbc96c2ee04ce4820687df52ab1`.
- Next is to finish the default suite and the explicit JIT-disabled demo check.

### Review verification

| Check | Result |
|---|---|
| `uv run --no-sync ruff check .` | Pass |
| `uv run --no-sync ruff format --check .` | Pass, 223 files |
| `uv run --no-sync mypy` | Pass, 135 source files |
| `uv run --no-sync lint-imports` | Pass, 14 contracts kept, 0 broken |
| `uv run --no-sync python scripts/generate_reference.py --check` | Pass, reference current |
| `uv run --no-sync python scripts/generate_ul_fund_slots.py --check` | Pass, generated source current |
| `uv run --no-sync python scripts/check_clean_install.py` | Pass, isolated runtime wheel and eight-policy TERM valuation |
| `uv build` | Pass, sdist and wheel. uv warned that its configured cache directory is inside the source directory. |
| `NUMBA_DISABLE_JIT=1 uv run --no-sync pytest tests/unit_linked -q --tb=short` | Pass, 196 tests, 1 deselected, 81.84 s |
| `NUMBA_DISABLE_JIT=1 uv run --no-sync pytest tests/unit_linked/test_unit_segment.py -m slow -q --tb=short --durations=1` | Pass, 1 test, 4 deselected, 23m 03s |
| `uv run --no-sync avk compile UNIT_LINKED` | Pass, 656 columns, one pass, all three bases |
| `uv run --no-sync pytest` | Pass, 416 tests, 9 deselected, 27m 16s |
| Saved result guard | Pass, all 171 saved files byte-identical to their HEAD blobs and the file set matches HEAD |

The inline review checked the working-tree diff against the three decisions,
the phase constraints and the unchanged ordinary-policy projection. Both
10,000-policy runs passed, and the existing 100,000-policy slow suite was
outside this review run. The 11 review files are in the working tree against
the first-pass commit `abd6688`, ready for orchestrator review.
