# Actuary Valuation Kit working notes

## Layout

- `src/avk/model` defines, compiles and executes formula components.
- `src/avk/products` composes the five built-in product families.
- `src/avk/inputs`, `assumptions`, `runs` and `outputs` implement the run
  contracts. Start with the public API in `src/avk/api.py` or with `avk --help`.
- `tests/regression` exercises complete products. `tests/saved/demo` holds
  approved tables from the invented demo. `docs/reference` is generated.

## Invariants

Keep the model independent of I/O, configuration and products. Formula modules
import the authoring API and other formula modules. Formulas declare one owner
per column, and replacements use `@override`. Factories compose products.
Compiled formulas use float64 and IEEE arithmetic without fastmath. Reduce in
fixed logical blocks of 1024 policies so that batch sizes and thread counts
preserve results. Load all inputs explicitly and validate before projection.
Writers format the ordered output schema and stream per-policy data.

Use `avk.testing.parity` for comparisons. Rates use relative tolerance 1e-12,
with an absolute floor of 1e-10 percentage points for rate columns ending in
`_change_pct`. Decrements use 1e-9 relative plus 1e-10 times scale. Other values
use 1e-6 relative plus 1e-8 times scale. Money has an absolute floor of 1e-5.
Identifiers and text match exactly. Never relax decrement tolerances.

Treat saved results as the numerical reference. A change needs maintainer
approval and a documented explanation of the affected results. Keep saved
tables byte-identical for documentation, naming and packaging changes. Keep
real policy and assumption data out of the repository and issue reports.

## Checks

From the project root, run:

```sh
uv sync --locked --extra ui --extra sql --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
uv run python scripts/generate_reference.py --check
uv run python scripts/check_clean_install.py
uv build
```

Run `uv run pytest -m slow` when changes affect projection or source layout.
See [contribution guidance](CONTRIBUTING.md) for the expected review evidence.
