# UL P1 log

Plan: `docs/superpowers/plans/2026-11-26-ul-p1-inputs.md`. Branch: `claude/ul-p1-inputs-d90104`
(the worktree branch the orchestrator created; the plan names `ul/p1-inputs`).

## Task 1: constants and field catalogue — done

- Files: `src/avk/products/unit_linked/{__init__,bindings,features}.py`,
  `tests/unit_linked/test_catalogue.py`.
- Test: `uv run pytest tests/unit_linked/test_catalogue.py -q` → 19 passed.
- Decisions:
  - `FieldRule` keeps the six fixed fields in order and adds two defaulted fields,
    `minimum_open` (unit_price > 0, alpha > -1) and `meaning` (documentation text).
  - Cap rates (`pac_max`, `fmc_max`, ...) are closed `[0, 1]` so `UNCAPPED` can state
    1 for rate maxima; `pac_ratio_max_first5` must be at least 1.
  - `bindings.py` also holds the other logical table names, `CHARGE_COLUMNS`
    (`Charge_Column` order), gender/smoker codes and the parameter names.
- Next: Task 2 (public formats).

## Task 2: public formats — done

- Files: `src/avk/inputs/public_formats.py` (`keyed` = `avk_ul_keyed_v1`, `year_key` =
  `avk_ul_year_key_v1`), `src/avk/inputs/registry.py` (BUILTIN_FORMATS for all eleven UL
  logical tables), `docs/inputs/public-formats.md`, regenerated `docs/reference/table-formats.md`,
  `tests/unit_linked/test_formats.py`.
- Tests: `uv run pytest tests/unit_linked/test_formats.py -q` → 20 passed;
  `uv run pytest tests/regression -q -k "format or input"` → 72 passed.
- Decisions:
  - Keyed files must hold exactly the declared fields (unknown fields rejected by name).
    Year-key files may hold several fields; each binding reads one (`ul_charge_scales/<field>`).
  - Field spellings go through the existing `field_name` (identity for the UL names).
- Separate commit `3c01e3f`: the base commit's plan file failed `ruff format --check`
  (Python code blocks in Markdown); reformatted, content unchanged.
- Next: Task 3 (demo basis tables).

## Task 3: demo basis tables — done

- Files: new `src/avk/demo/unit_linked.py` (fund universe, variants, regimes, scales,
  rates, parameters, `ul_basis(put, mortality)`), `src/avk/demo/generate.py` (calls it,
  appends UNIT_LINKED parameter rows, keeps UL tables out of other products' configs),
  `src/avk/demo/README.md`, eleven new `examples/demo/basis/*ul*.csv` files and 27
  appended rows in `examples/demo/basis/product_parameters.csv`,
  `tests/unit_linked/test_demo_basis.py`.
- Tests: `uv run pytest tests/unit_linked/test_demo_basis.py -q` → 6 passed (6 failed
  against the old generator); `tests/regression/test_demo_suite.py`,
  `tests/regression/test_demo_inputs.py` and `tests/unit_linked` → 144 passed.
- Decisions:
  - Existing basis files compared with the parity helper, as the repository's own test
    does: on Windows `exp()` differs in the last digit from the committed (Linux) files.
    Existing committed files were not rewritten.
  - Variant ids 0-5 in plan order; regime ids IRDAI_2024 0, UNCAPPED 1.
  - Invented scales: WEALTH_T2 allocation 5/4/4/3/3%, 1.5% to year 10, admin 250/200,
    loyalty 0.2% from year 6, booster 1% every fifth year from 10; MATURITY_GUARANTEE
    allocation 7/5/5/4/4%, 2% to 10, 1% after, admin 220; SINGLE 3% flat (a flat scale
    keeps the first-five-year ratio rule meaningful), admin 150; LIMITED_PAY_ROC
    8/6/6/4/4%, admin 300 then 250, 3% escalation; INVESTMENT_BOND 1% and 100, no
    discontinuance charge. Every capped variant uses the cap discontinuance scale.
  - UNCAPPED: 1 for rate maxima, 1e12 for amounts and ratios, 0 for minimums.
  - Lapse years 2-4 are 7/6/5%, years 6-10 9/8.25/7.5/6.75/6%.
- Next: Task 4 (companion-table hook).

## Task 4: companion-table hook — done

- Files: `src/avk/products/registry.py` (`companion_tables = ()`, `companion_adapter`),
  `src/avk/inputs/validation.py` (`validate_companions`, `companion_orphans` defaults),
  `src/avk/runs/check.py` (`_prepare`: read companions once into `CheckReport.companions`,
  validate per batch, prepare with `companion_adapter`, orphan check after the whole
  book), `tests/unit_linked/test_companions.py`.
- Tests: `test_companions.py` → 6 passed (6 failed before); `test_demo_suite.py`,
  `test_parquet.py` and `tests/unit_linked` → 127 passed (existing saved results unchanged).
- Decisions:
  - Deviation (additive): `PolicyValidator.companion_orphans(known, companions)`. A
    streamed batch sees only its own policies, so holdings naming no policy are
    reported once after all batches; `known(numbers)` tests membership in the book
    (CSV: the prepared `Policy_Number`; Parquet: the existing SQLite id index).
  - Companion validation runs only after the policy rows pass, and its errors are
    raised as one `InputError` before any preparation.
- Next: Task 5 (validation).

## Task 5: policy, holdings and cap validation — done

- Files: `src/avk/products/unit_linked/validation.py`, `tests/unit_linked/conftest.py`
  (valid six-policy book; demo tables loaded as the run binds them),
  `tests/unit_linked/test_validation.py`.
- Test: `uv run pytest tests/unit_linked/test_validation.py -q` → 65 passed.
- Decisions:
  - Deviation: `check_policies_against_tables(policies, holdings, tables)` takes the raw
    policy and holding rows (the plan wrote `(prepared, tables)`). Rules that need
    `ul_funds` move there from the holdings validator: Fund Code exists (exact match),
    at most `MAX_FUND_SLOTS` holdings outside the DPF, the DPF holding rules, zero
    allocation to non-selectable funds. They raise at preparation in the same
    joined `InputError`.
  - Valuation-date rules (Valuation Date equals the run date, start and status dates
    not after it) are in `validate_at`, which sees the run date.
  - A zero allocation year among the first five fails the ratio rule unless all five
    are zero. Sum-assured minimum uses the regular multiples for regular and limited
    pay and the single multiples (of the single premium) for single premium.
  - Extra rules: term positive, payment term at most the term, EMR positive, integer
    columns integral, code columns (Profitability Group, Transition Approach) in range,
    Measurement Model VFA or GMM, variant single_premium agrees with frequency 0.
- Next: Task 6 (preparation).

## Task 6: model-point preparation — done

- Files: `src/avk/products/unit_linked/preparation.py` (`UnitLinkedModelPointAdapter`),
  `src/avk/products/unit_linked/formulas.py` (committed here because it spells the
  field contract `FIELDS`), `tests/unit_linked/test_preparation.py`.
- Test: `uv run pytest tests/unit_linked/test_preparation.py -q` → 8 passed.
- Decisions:
  - The field list lives in `formulas.py` (formula modules may import only the authoring
    API); `preparation.PREPARED_FIELDS` is that tuple. 32 policy fields, 26 `V_*`, 3
    `R_*`, 13 DPF fields, 5 x 18 slot fields = 164 fields, exactly the plan's list.
  - `Policy_Status` is Float64 (the streamed spool casts it so); `Gender_Code`,
    `Smoker_Code`, `Charge_Column`, ids, terms, counts and `Fund_k_Present`/`Fund_k_Fund_Index`
    are Int64; everything else Float64. `V_*` keep the table's float values.
  - `DPF_FMC`/`DPF_Alpha`/`DPF_W_*` come from the DPF row of `ul_funds` for every policy;
    `DPF_Value` is Units x DPF unit price for the status-1 policy, else 0.
  - Table rules (`check_tables`) run once per adapter; policy-against-table rules per batch.
  - The run-layer Parquet parity and cross-batch orphan tests are in Task 7's test file.
- Next: Task 7 (skeleton product, factory, demo book).

## Task 7: skeleton product, factory, registration and demo book — done

- Files: `src/avk/products/unit_linked/{formulas,factory,output_columns}.py`,
  `src/avk/products/registry.py` (registers `UnitLinkedFactory`), new
  `src/avk/demo/unit_linked_book.py` (`ul_book`, `generate_ul`), `src/avk/demo/generate.py`
  (UNIT_LINKED branch and CLI choice; `PRODUCTS` unchanged), `src/avk/demo/README.md`,
  `tests/unit_linked/test_skeleton_run.py`. `src/avk/cli.py` untouched (the CLI takes its
  choices from `add_generate_arguments`).
- Tests: `uv run pytest tests/unit_linked -q` → 135 passed (skeleton tests 11, 3 of which
  failed with the registration removed). Ruff, format, mypy, import contracts pass.
- Behaviour: `avk compile UNIT_LINKED` (5 columns, 1 pass, bases reserving/be/mc);
  200-policy demo passes `avk check`; `avk run` writes `funds_opening_unit_fund` and
  `funds_opening_dpf_fund` (aggregate and seriatim) whose step-0 values equal
  Units x unit price over the holdings (parity money class); StressCapital and IFRS17
  fail with `UNIT_LINKED supports the Valuation run type only`.
- Decisions:
  - Output names `funds_opening_unit_fund`, `funds_opening_dpf_fund`, basis-independent.
  - Keyed and year-key tables load as `UnitLinkedTableAssumption` (factory module).
  - Year-key bindings: `ul_charge_scales/<field>` (keymap Variant_Id),
    `ul_disc_charge_caps/<field>` and `ul_riy_caps` (keymap Regime_Id), policy-year axis
    clamped both ends. Channel tables read value column `rate`.
  - Demo book (10k seed 209): status 1 3.2%, status 2 4.5%; 1-5 funds 33/34/19/10/5%;
    single-premium variants ULIP_SINGLE and UL_INVESTMENT_BOND, limited pay ROC or
    CLASSIC, regular CLASSIC/WEALTH_T2/MATURITY_GUARANTEE; currency INR; Policy Numbers
    `UL0000001`...; status-2 cessation within the last 36 months after the lock-in.
  - `generate(folder, "UNIT_LINKED", ...)` writes policies.csv, policy_funds.csv, basis/
    and valuation.json only.
- Next: Task 8 (documentation) and the full check list.
