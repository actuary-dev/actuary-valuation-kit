# Add a table format through a plug-in
Complete [the Term tutorial](term.md). Suppose your mortality spreadsheet has
columns `age,m,f,x` instead of the public long format `age,field,value`.
The values are annual probabilities as fractions, not percentages.

1. Open [formats.py](package/src/tutorial_products/formats.py).
   The reader sorts and checks consecutive unique ages, converts the three sex
   columns to the required order, then returns a table with the declared age and
   sex lookup axes. Product-level assumption validation still checks probabilities.
2. The `avk.formats` entry point in the tutorial
   [pyproject.toml](package/pyproject.toml) publishes `tutorial_mortality`.
   The exercise runner installs this package in its disposable folder.
3. [table_format.py](table_format.py) pivots the generated public mortality table
   into 121 rows for ages 0 through 120, preserving its nonzero, age- and
   sex-varying annual probabilities. For example, at age 35 the rates are
   **0.0004700** male, **0.0003854** female and **0.0004277** transgender.
   It uses two invented policies: male age 35 with cover 1,000, and female
   age 45 with cover 2,000, both with annual premium 100. Distinct ages and
   covers prevent errors from cancelling in the aggregate.
   Unlike the flat-rate Term example, this run retains generated mortality;
   lapses and reinsurance mortality remain zero. It selects the reader with
   `Inputs.Replace.mortality.Format = "tutorial_mortality"` and the new file's
   absolute `Path`. Run from the project root:

```sh
uv run python docs/tutorials/table_format.py /tmp/avk-format-tutorial
```

PowerShell:

```powershell
uv run python docs/tutorials/table_format.py "$HOME/avk-work/tutorial-format"
```

4. The runner checks, compiles and runs the tutorial product with both layouts.
   It compares every aggregate column using Actuary Valuation Kit's central tolerance policy.
   Expected future premiums **199.89219918**, death benefits **3.72784445**,
   step 1 closing lives **1.999901974265**.
   Guard 2 repeats the full run with male/female columns swapped and with ages
   shifted by one; each must fail aggregate comparison. Last line: `PASS: wide mortality hook preserves every aggregate column`.
   The public Term policy contract accepts only male and female policies.
   The runner additionally compares all 121 ages and all three sex columns
   through the public format reader boundary, using central rate tolerances;
   this exercises the transgender column without changing the engine.
   Both configurations, the wide CSV and the results stay in your chosen folder.

For deployment, install your reader package into the same environment as Actuary Valuation Kit
and restart Python. See [the full reader contract](../developer/table-format-plugins.md)
for collisions, input errors, shape, units and boundary rules.
