# UL P6a implementation log

## Baseline

- Clean starting branch `ul/p6a-unit-features`, with no phase log to resume.
- `uv run --no-sync avk demo generate .tmp/p6a-demo --product UNIT_LINKED --count 10000 --seed 209`
  and `uv run --no-sync avk run .tmp/p6a-demo/valuation.json` completed before
  engine edits. The run used all three bases, one path and 372 months. The
  aggregate SHA-256 is `5567bbc268c2e7ca336e1c076300cb8f65077d1929e50342cad142a888b71deb`.
  The seriatim SHA-256 is `4b18aed3507b26189919337772f0086f8f2efc814fc540314b040a80192bc858`.
- Both maintainer specifications leave these extensions outside the reference
  projection. The phase plan records implementation conventions.

## Task 1 — Top-up payments, cover and withdrawal lock

- Files: UL bindings, features, validation, preparation, formulas, premiums,
  paid-up, DPF and generated slots, the slot generator, UL demo basis generator
  and two basis tables, and UL top-up, catalogue and preparation tests.
- The initial `NUMBA_DISABLE_JIT=1 uv run --no-sync pytest tests/unit_linked/test_topups.py -q --tb=short`
  failed all five new cases on the missing formula columns and validation. With
  JIT disabled, `uv run --no-sync pytest tests/unit_linked/test_topups.py tests/unit_linked/test_validation.py tests/unit_linked/test_preparation.py -q --tb=short`
  passed 79 tests.
- The regular amount is per base instalment. All top-up units share a
  policy-level withdrawal lock starting from the most recent top-up. Top-up
  cover is part of insured cover before the Type I or II calculation and is
  retained on conversion to paid-up. Typical opening histories already report
  top-ups within total premiums paid. The variant enables top-up inputs.
- Added zero defaults to the demo variant and charge scale basis files.
  The seed-209 policy and holding generators retain their existing data.
- Next is lifecycle and systematic transfer.

## Task 2 — Lifecycle and systematic fund transfers

- Files: UL bindings, features, validation, preparation, strategies, formulas,
  factory and benefits, slot generator and generated slots, input format registry,
  demo basis and generation, and UL catalogue, preparation and strategy tests.
- The first JIT-disabled strategy run failed all eight new cases on the missing
  transfers, diagnostics and policy checks. With JIT disabled,
  `uv run --no-sync pytest tests/unit_linked/test_strategies.py tests/unit_linked/test_topups.py tests/unit_linked/test_validation.py tests/unit_linked/test_preparation.py tests/unit_linked/test_demo_basis.py -q --tb=short`
  passed 93 tests.
- The table has a zero strategy. A lifecycle strategy rebalances the designated
  equity and debt sleeve at the first live step and at policy-year starts.
  STP runs monthly from opening units. Only positive gross sales can incur a
  switch charge, limited by sale proceeds. Sales and purchases preserve top-up
  tagging, including during lock-in. Added the off strategy to the demo basis.
- Next is highest-NAV maturity guarantee and reporting.

## Task 3 — Highest-NAV maturity guarantee

- Files: UL features, preparation, formulas, benefits, factory, output columns
  and slot generator, demo variant basis and generator, product factory and
  Valuation schema hook, and UL highest-NAV, catalogue and preparation tests.
- The first JIT-disabled highest-NAV run failed all seven new cases on missing
  prices or output columns. With JIT disabled,
  `uv run --no-sync pytest tests/unit_linked/test_highest_nav.py tests/unit_linked/test_topups.py tests/unit_linked/test_strategies.py tests/unit_linked/test_benefits.py -q --tb=short`
  passed 30 tests.
- The window starts in the selected inclusive policy month. Opening price is
  the fund universe's spot NAV, and the holding's historical price seeds the
  peak. The price and peak evolve independently by fund, basis and path.
  Both active and paid-up maturities draw from the guarantee. A policy-level
  GMMB treats the highest-NAV payment as part of the minimum already paid.
- The Valuation factory adds the separately reported cost when the book has
  the guarantee enabled on a highest-NAV holding. The default factory still
  returns its existing schema. P2b receives this outgo from the existing port.
- Next is public contract documentation, compatibility proof and full checks.

## Task 4 — Documentation and verification

- Documented the new policy and holding fields, assumption tables, settlement
  conventions and output in `docs/products/unit-linked.md` and the format index.
- Added combined preflight and Valuation coverage for one active policy using
  top-ups and STP, an explicit paid-up conversion calculation, and a paid-up
  NAV calculation with FMC and mortality. Preflight rejects missing enabled
  fields, a backdated payment, incomplete allocation, invalid slots and
  weights, and both charge-cap breaches.
- With `NUMBA_DISABLE_JIT=1`, `uv run --no-sync pytest tests/unit_linked/test_topups.py tests/unit_linked/test_strategies.py tests/unit_linked/test_highest_nav.py -q --tb=short`
  passed all 30 new tests.
- The same command with JIT enabled passed all 30 tests in 188.76 s.
- `uv run --no-sync pytest tests/unit_linked -q --tb=short` passed 226 tests
  with one slow test deselected in 712.17 s.
- `uv run --no-sync pytest tests/unit_linked/test_unit_segment.py -m slow -q --tb=short`
  passed the 10,000-policy reconciliation test, with four deselected, in 49.76 s.
- `uv run --no-sync python .tmp/p6a-verify-bytes.py` verified that all 171
  `tests/saved` files match HEAD byte-for-byte, with the same file set.

| Check | Result |
|---|---|
| `uv run --no-sync ruff check .` | Pass |
| `uv run --no-sync ruff format --check .` | Pass, 229 files |
| `uv run --no-sync mypy` | Pass, 136 source files |
| `uv run --no-sync lint-imports` | Pass, 14 contracts kept, 0 broken |
| `uv run --no-sync pytest` | Pass, 446 tests, 9 deselected, 5,105.05 s |
| `uv run --no-sync pytest -m slow` | Pass, 7 tests, 448 deselected, 5,451.35 s |
| `uv run --no-sync python scripts/generate_reference.py --check` | Pass |
| `uv run --no-sync python scripts/generate_ul_fund_slots.py --check` | Pass |
| `uv run --no-sync python scripts/check_clean_install.py` | Pass, isolated wheel and eight-policy TERM valuation |
| `uv build` | Pass, sdist and wheel. uv warned that its cache is inside the source tree. |

### Seed-209 byte comparison

Generated the after book with the same 10,000-policy, seed-209 command in
`.tmp/p6a-demo-after` and ran its unmodified Valuation file on all three
bases. `uv run --no-sync python .tmp/p6a-verify-bytes.py --demo` compared raw
bytes of the inputs and outputs in the before and after folders.

| File | Equal bytes | SHA-256, both runs |
|---|---:|---|
| Policies | 2,675,901 | `5079012c1ecabe56e0e0daef7a12a40e0d545a9115a5ff4372bef4e022fceeb6` |
| Holdings | 2,477,199 | `bf7b01db0721bb62ebe183e5dbb88816ff4d647a09365df2c06d3b3088aac43d` |
| Aggregate | 872,539 | `5567bbc268c2e7ca336e1c076300cb8f65077d1929e50342cad142a888b71deb` |
| Seriatim | 297,584 | `4b18aed3507b26189919337772f0086f8f2efc814fc540314b040a80192bc858` |

The cold CLI compile changed from 74.73 s to 349.66 s, kernel identities
`7d8aaeb0d3a84404` and `a894c43fa23c57fa`. The after run overlapped the
repository test suites. Its recorded projection time includes first-use
Numba compilation for the actual input layout.
On a repeat run with the signatures cached, the after kernel loaded in 2.18 s,
projected in 4.13 s, and took 8.93 s in total. Both warm-run output hashes
matched the cold run. Cold compilation remains the performance trade-off.

### Working-tree files

- New documentation: `2026-11-27-ul-p6a-unit-features.md` and this log.
  Updated `docs/products/unit-linked.md` and `docs/inputs/public-formats.md`.
- New strategy loader and rules in `src/avk/products/unit_linked/strategies.py`.
  Updated `benefits.py`, `bindings.py`, `dpf.py`, `factory.py`, `features.py`,
  `formulas.py`, `fund_slots.py`, `output_columns.py`, `paid_up.py`,
  `premiums.py`, `preparation.py` and `validation.py` in the same package.
- Updated `scripts/generate_ul_fund_slots.py`, `src/avk/demo/unit_linked.py`,
  `src/avk/inputs/registry.py`, `src/avk/products/registry.py` and
  `src/avk/runs/valuation.py`.
- New `examples/demo/basis/ul_strategies.csv`. Added off settings to the
  existing `ul_variants.csv` and `ul_charge_scales.csv`.
- New `tests/unit_linked/test_topups.py`, `test_strategies.py` and
  `test_highest_nav.py`. Updated `conftest.py`, `test_catalogue.py`,
  `test_demo_basis.py` and `test_preparation.py` in that suite.

The slow suite covered the shared input registry and the default-preserving
Valuation schema hook. The scope review found no diff to decrements, P2b
modules, saved results or the demo policy and holding generators. All phase
checks are complete. The working-tree changes are ready for orchestrator review.
