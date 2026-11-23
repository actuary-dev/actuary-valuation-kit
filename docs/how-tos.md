# How to run analyses
See [nested analysis keys](reference/analysis-settings.md) for case, stress and IFRS settings.
Start in the package directory after installation. Generate a public book once
with the README command. It writes five complete JSON configurations:
`valuation.json`, `cases.json`, `capital.json`, `measurement.json` and
`rollforward.json`. Each writes to a separate subfolder under `output`.

## Command line
On Linux replace `BOOK` below with your generated folder; on Windows use
a quoted path such as `"$HOME/avk-work/demo-term/cases.json"`.

```sh
uv run avk check BOOK/cases.json
uv run avk run BOOK/cases.json
uv run avk run BOOK/capital.json
uv run avk run BOOK/measurement.json
uv run avk run BOOK/rollforward.json
uv run avk compile TERM --explain
```

A case has `Name`, optional `Shocks`, optional `Overrides`.
Set `Inputs.Tables` to the table list and define sensitivity cases under `Cases`.
The generated case multiplies mortality by 1.15. Overrides can select tables,
product parameters, curves, valuation date and policy data; read the complete
[override contract](../src/avk/runs/overrides.py) before composing them.
Cases use the same validated projection as the base. Expense shocks affect
expense schedules and exclude commission.

Stress capital uses `Run_Type: StressCapital` and `Stress_Set`, with `Cases`,
`Correlation` and `Settings`. Settings include `Aggregation` (`policy` or
`portfolio`), `Cost_of_Capital_Rate`, `Discount_Curve` and optional
`Diversification_Floor`, `Operational_Risk`, `Cost_Loading`.
Lapse up/down/mass-lapse risks combine into a single lapse risk.
See the [capital notebook](../notebooks/capital.ipynb) for worked results.
[Life](../src/avk/presets/solvency_ii_life.yaml) and
[rider](../src/avk/presets/solvency_ii_riders.yaml) presets retain their
calibration citations; review suitability before using any preset.

IFRS 17 uses `Run_Type: IFRS17` and an `IFRS17` block:
`Reporting_Months` (1..120), `Locked_In_Curves`, `Current_Curve`,
`Profitability_Field`, `RA_Method` and signed `RI_RA_Ratio`.
Optional `Portfolio_Field` and `Cohort_Field` select existing policy columns.
For `RA_Method: ratio`, supply nonnegative `RA_Ratio`; for
`cost_of_capital`, supply `Stress_Set` instead.
The demo uses 0.08 direct RA ratio and -0.05 held RA ratio.
`Roll_Forward` requires `Opening` (date and policy-data overrides) and
`Opening_Balances` (logical table). Additional cases are excluded in a
roll-forward. The generated example moves from 2025-12-31 to 2026-06-30.
See [the bridge notebook](../notebooks/rollforward.ipynb).

## Python API
This complete script runs an invented book and prints the files written:

```python
from pathlib import Path
from tempfile import mkdtemp

from avk.api import check, run
from avk.demo.generate import generate

folder = Path(mkdtemp(prefix="avk-api-"))
config = generate(folder, "TERM", 10000, 209)
check(config)
result = run(config)
for path in result.files:
    print(path)
```

`run` also accepts a `RunConfig`, an output override, progress callback and
diagnostics folder. Use diagnostics only for small books: every policy-month
column can be large. A `AvkError` identifies a checked input/configuration,
formula, kernel or output error. Preserve the logs when reporting a failure.

## Change table storage or product
Generate with `--product ACCIDENTAL_DEATH_RIDER`, `CRITICAL_ILLNESS_RIDER`,
`DISABILITY_RIDER` or `CREDIT_LIFE` for another public book.
CSV and Parquet policy files use the same field contract;
see [Parquet policies](inputs/parquet-policies.md).
Use [public formats](inputs/public-formats.md) for table columns and units.
Do not replace absent assumptions with zeros. Use the demo generator for a
complete invented starting point and replace only reviewed inputs.
