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
