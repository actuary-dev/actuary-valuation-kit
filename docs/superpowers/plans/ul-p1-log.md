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
