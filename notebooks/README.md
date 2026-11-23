# Worked notebooks
Install from the package directory with `uv sync --locked --extra ui --dev`.
Open any notebook in your Jupyter-compatible editor using that environment.
Run all cells in order; inputs/results go to a new temporary folder printed by the notebook.
No real data or stored outputs are included.

- [Valuation and sensitivities](valuation.ipynb): held reserve run-off and a mortality case.
- [Stress capital and risk margin](capital.ipynb): risk charges and future holding costs.
- [IFRS 17 roll-forward](rollforward.ipynb): the six-month group CSM bridge and closing measures.

Headless execution, from the project root (Linux or PowerShell):
```sh
uv run pytest -q tests/regression/test_tutorials.py
```
This is Guard 2; it also builds and runs all three tutorial products.
Notebook copies execute in temporary folders; source notebooks remain output-free.
