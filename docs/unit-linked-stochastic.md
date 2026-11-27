# Stochastic UNIT_LINKED valuation

This example projects an invented 200-policy book under eight risk-neutral
scenarios. It summarizes the portfolio cashflows, measures the time value on a
unit benefit, and reruns the same paths with dynamic lapse.

Save the Python blocks in order in one script and run it from the project root
with `uv run --no-sync python <script>`.

## Generate the book and paths

Use the deterministic `reference_forward` curve as the risk-neutral drift for
all ten asset classes. Vary large-cap equity at 18% annual volatility and set
the other asset volatilities to zero. Zero volatility in the risk-neutral
generator still uses its risk-free drift. The correlation matrix is the identity.

The P2a MC projection with `mc_fund_return_source = 1` uses the scenario returns
and fund alpha. Set the invented fund alphas to zero for both projections so
that the asset drift and the reference path use the same growth assumption.
The certainty-equivalent projection uses `mc_fund_return_source = 0`.

```python
import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import polars as pl

from avk.api import check, run, tvog
from avk.demo.generate import generate

folder = Path(".tmp/ul-stochastic-tutorial").resolve()
reference_run = generate(folder, "UNIT_LINKED", 200, 209)

funds = folder / "basis/ul_funds.csv"
pl.read_csv(funds).with_columns(
    pl.when(pl.col("field") == "alpha").then(0.0).otherwise(pl.col("value")).alias("value")
).write_csv(funds)

reference_scenarios = check(reference_run).scenarios
assets = [name for name in reference_scenarios.variables if name.startswith("ret_")]
with (folder / "assets.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["variable", "volatility"])
    writer.writerows((name, 0.18 if name == "ret_eq_large" else 0.0) for name in assets)
with (folder / "correlations.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["risk", "other", "value"])
    writer.writerows((a, b, int(a == b)) for a in assets for b in assets)

config = json.loads(reference_run.read_text(encoding="utf-8"))
parameters = folder / "basis/product_parameters.csv"
path_parameters = folder / "path_parameters.csv"
pl.read_csv(parameters).with_columns(
    pl.when((pl.col("product") == "UNIT_LINKED") & (pl.col("parameter") == "mc_fund_return_source"))
    .then(1.0)
    .otherwise(pl.col("value"))
    .alias("value")
).write_csv(path_parameters)
config["Inputs"]["Replace"]["product_parameters"]["Path"] = str(path_parameters)
config["Inputs"]["Scenarios"] = {
    "Source": "generator",
    "Generator": "MultiAssetLognormalESG",
    "Settings": {
        "Scenarios": 8,
        "Seed": 209,
        "Measure": "risk_neutral",
        "Assets": "assets.csv",
        "Correlations": "correlations.csv",
        "Risk_Free": "reference_forward",
        "Antithetic": True,
    },
}


def write_config(name):
    path = folder / name
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


generator_run = write_config("generator.json")
paths = folder / "risk_neutral.parquet"
subprocess.run(["avk", "scenarios", "generate", str(generator_run), str(paths)], check=True)
```

## Run and summarize the portfolio

Supply the saved paths so each rerun uses identical economic inputs. Request the
50th and 95th percentiles and the upper-tail CTE at 95% confidence. The latter
averages the highest 5% probability mass, using part of the boundary path when
necessary. The largest path outcome determines this 5% tail in an eight-path,
equally weighted example.

```python
config["Inputs"]["Scenarios"] = {
    "Source": "parquet",
    "Path": str(paths),
    "Settings": {"Measure": "risk_neutral"},
}
config["Scenario_Summary"] = {"Percentiles": [0.5, 0.95], "CTE_Levels": [0.95], "Tail": "upper"}
stochastic_run = write_config("stochastic.json")
scenarios = check(stochastic_run).scenarios
run(stochastic_run, output=folder / "stochastic")

summary_file = folder / "stochastic/UNIT_LINKED_Base_scenario_summary.csv"
summary = pl.read_csv(summary_file)
print(
    summary.filter(
        (pl.col("Output_Column") == "funds_total_MC") & (pl.col("Projection_Step") == 12)
    ).write_csv()
)
```

Each summary row represents one aggregate output column at one projection step.
The file follows the aggregate schema order, then ascending step. Its columns
are the step, `Output_Column`, `Mean`, and the requested `P_<level>` and
`CTE_<level>` in configuration order. AVK uses supplied scenario weights or
equal weights when the file has no `Weight` column. A percentile is the smallest
value whose cumulative weight reaches its level. Level zero gives the minimum
and level one gives the maximum. An empty list omits that statistic. Use
`Tail: lower` to average the lowest `1 - level` probability mass. An undefined
positive-weight path result leaves the statistics blank for that column and step.
In this run the month-12 mean MC fund is about 364.58 million, and both the
95th percentile and its upper-tail CTE are about 381.43 million.

## Compare with the certainty equivalent

Run the same book on the deterministic reference-forward path. For this
example, the chosen payment is the active unit maturity benefit. Each payment
falls at month end, so discount its aggregate cashflow with the cumulative
product of monthly gross forward rates from month 1. Compute one PV for each
path, then subtract the deterministic PV from their probability-weighted mean.

```python
run(reference_run, output=folder / "reference")
aggregate_name = "UNIT_LINKED_Base_aggregate_output.csv"
benefit = "benefits_unit_active_maturity_MC"
risk_neutral = pl.read_csv(folder / "stochastic" / aggregate_name)
reference = pl.read_csv(folder / "reference" / aggregate_name)


def maturity_pv(rows, forward):
    payments = rows.sort("Projection_Step")[benefit].to_numpy()
    return float(np.sum(payments[1:] / np.cumprod(1 + forward[1:])))


path_pvs = [
    maturity_pv(
        risk_neutral.filter(pl.col("Scenario") == int(scenario)),
        scenarios.variables["reference_forward"][index],
    )
    for index, scenario in enumerate(scenarios.ids)
]
ce = maturity_pv(reference, reference_scenarios.variables["reference_forward"][0])
print(
    f"Reference PV {ce:,.2f}. TVOG on the chosen unit benefit {tvog(scenarios, path_pvs, ce):,.2f}."
)
```

This example demonstrates the calculation on an existing unit cashflow. To
measure TVOG on guarantee outgo, supply the maturity and DPF guarantee-cost
PVs computed on their respective MC paths. The helper applies the same
risk-neutral mean less certainty-equivalent convention to any matched PVs.
Eight paths are illustrative. Assessment of sampling error requires more paths.
The reference PV in this example is 379,075,063.52 and the difference is
2,146,137.98 in the demo currency.

## Turn on dynamic lapse

Enable the switch for the MC basis for a comparison on the same paths.
Set the switch and parameters explicitly for each basis. Omitting the entire
`Dynamic_Lapse` block disables the feature.

```python
off = {"Enabled": False, "Slope": 2.0, "Floor": 0.5, "Cap": 1.5}
config["Dynamic_Lapse"] = {"reserving": off, "be": off, "mc": {**off, "Enabled": True}}
run(write_config("dynamic.json"), output=folder / "dynamic")

dynamic = pl.read_csv(folder / "dynamic" / aggregate_name)
column = "surrenders_active_MC"
print(
    risk_neutral.select("Scenario", "Projection_Step", pl.col(column).alias("Off"))
    .join(
        dynamic.select("Scenario", "Projection_Step", pl.col(column).alias("On")),
        on=["Scenario", "Projection_Step"],
    )
    .filter(pl.col("Projection_Step") == 12)
    .sort("Scenario")
    .write_csv()
)
```

The multiplier is `clip(1 + Slope * (moneyness - 1), Floor, Cap)`.
Moneyness is opening fund value divided by opening premiums paid. The model
uses balances per active life and aggregate balances for the paid-up cohort.
With zero opening premiums paid the multiplier is one. With a positive slope
and bounds spanning one, a lower fund value reduces surrender, reflecting the
higher relative value of the guarantee proxy. The adjusted monthly ordinary
surrender probability is capped at one. Premium cessation, DPF rules, and the
case mass-lapse parameter keep their existing formulas. For a TVOG comparison
with dynamic lapse enabled, apply the same lapse settings to the CE projection.
At month 12 the expected active surrenders are about 0.7304 on each path with
the switch off, and range from 0.8298 to 0.9679 with it on.
