
# Economic scenarios

A valuation uses the product's declared monthly economic variables. When
`Inputs.Scenarios` is absent, `DeterministicCurveESG` converts the selected
annual-effective curves to monthly-effective rates and applies the product's
timing rules. The deterministic generator takes no settings.

For a stochastic valuation, select `MultiAssetLognormalESG` in the run file or
supply a Parquet file. Stochastic and supplied valuations write a leading
`Scenario` column in their reporting tables. Use a single-product Valuation
configuration without Cases for these runs.

## Multi-asset model

The generator builds the same baseline paths as `DeterministicCurveESG`.
Variables listed in `Assets` get correlated lognormal returns. The other
variables, month zero and months outside each variable's declared placement
retain their baseline values. A 0% rate in a placed month can still vary.

For an active month, the monthly return is
`expm1(log1p(mu) - sigma²/2 + sigma * Z)`, where `sigma` is annual volatility
divided by `sqrt(12)`. The correlated standard normal shocks `Z` are independent
across months. Their contemporaneous correlations come from the supplied matrix.
The expected gross return is `1 + mu`.

- `real_world` uses each asset's own baseline monthly return for `mu`.
- `risk_neutral` uses the deterministic `Risk_Free` monthly rate for `mu`.
  When the asset compounds over the same months as the discount curve, its
  expected discounted index is one.

The settings belong under `Inputs.Scenarios.Settings`. CSV paths are relative
to the run file unless absolute.

| Setting | Value |
|---|---|
| `Scenarios` | Positive integer. |
| `Seed` | Nonnegative integer. |
| `Measure` | `real_world` or `risk_neutral`. |
| `Assets` | CSV with exactly `variable,volatility`. Each asset must be a distinct declared variable. Volatility is an annual fraction, finite and nonnegative. |
| `Correlations` | CSV with `risk,other,value` and every ordered pair of asset variables, including the diagonal. The matrix must be symmetric, have a unit diagonal and be positive semidefinite. Singular matrices are supported. |
| `Risk_Free` | Required for `risk_neutral`. Names a declared variable outside `Assets`. Omit this setting for `real_world`. |
| `Antithetic` | Optional Boolean, defaults to `false`. With `true`, the count must be even. Consecutive scenarios share a random stream and use opposite shocks. |

The generator uses PCG64 with NumPy child seed sequences. Increasing the path
count preserves the existing paths when the seed and other settings are held
fixed. Paths have equal weights. A generated file's `Seed` is an unsigned
64-bit token derived from each child sequence, shared within an antithetic
pair. Use the run's original `Seed` setting and model inputs to reproduce a set.

## TERM example

Generate an invented book.

```sh
uv run avk demo generate demo-term --product TERM --count 50 --seed 209
```

Save `demo-term/assets.csv` with the annual volatility of `roi`.

```csv
variable,volatility
roi,0.02
```

Save `demo-term/correlations.csv` with its one-variable correlation matrix.

```csv
risk,other,value
roi,roi,1
```

Add this `Scenarios` entry inside the existing `Inputs` object in
`demo-term/valuation.json`.

```json
{
  "Scenarios": {
    "Source": "generator",
    "Generator": "MultiAssetLognormalESG",
    "Settings": {
      "Scenarios": 4,
      "Seed": 209,
      "Measure": "real_world",
      "Assets": "assets.csv",
      "Correlations": "correlations.csv"
    }
  }
}
```

Run the valuation directly or export the same four paths to reuse.

```sh
uv run avk run demo-term/valuation.json
uv run avk scenarios generate demo-term/valuation.json demo-term/paths.parquet
```

To run again using the file, replace the `Scenarios` entry and rerun the valuation.

```json
{
  "Scenarios": {
    "Source": "parquet",
    "Path": "paths.parquet",
    "Settings": {"Measure": "real_world"}
  }
}
```

## Supplied Parquet format

Each row holds integer `Scenario`, integer `Seed`, integer `Month` and one
monthly-effective rate column per declared variable. Include every month from
zero to `Projection_Term * 12 - 1`, once per scenario, with a constant seed.
An optional numeric `Weight` column supplies the scenario probability. Repeat
it for every month in the path, use finite values between zero and one, and
make the per-scenario weights sum to one. AVK assumes equal weights if the
column is omitted. It reads rows in scenario-number and month order. Set
`Measure` in the receiving run file to match the measure used to build the paths.

`avk scenarios generate RUN_FILE OUTPUT.parquet` uses the run's generator,
defaulting to the deterministic curves. A deterministic export has scenario
number 1 and seed 0. To consume a deterministic file as a single-path
scenario valuation, use `Settings: {"Measure": "real_world"}`.

## Deterministic scenario library

`avk scenarios library RUN_FILE LIBRARY.json OUTPUT_FOLDER` starts each entry
from the product's deterministic curves and applies its operations in the
listed order. It writes one `<Name>.parquet` file per entry with scenario
number 1 and seed 0. Use letters, digits, underscores and hyphens in names,
with a distinct filename per entry.

| Operation | Fields and effect |
|---|---|
| `flat` | `Variables`, `Annual`. Sets the rate to the monthly equivalent of the given annual-effective rate. |
| `shift` | `Variables`, `Annual_Change`. Converts the rate to annual-effective space, adds the change and converts back. The resulting annual rate must exceed −100%. |
| `shock` | `Variables`, `Month`, `Factor`. Multiplies that month's gross return by a positive factor. A factor of `0.7` multiplies the existing gross return by 70%. |
| `custom` | `Path`. Reads a CSV with `Month` and one or more variable columns containing monthly-effective rates. Supply all months including zero. Relative paths are resolved from the library JSON file. |

`flat` and `shift` operate from month 1 on the product's placed months, including
any placed 0% rates. `shock` and `custom` can explicitly change month zero or a
month outside the curve placement.

Save this as `demo-term/library.json` for two illustration paths and a one-off fall.

```json
[
  {"Name": "illustration_4", "Operations": [
    {"Op": "flat", "Variables": ["roi"], "Annual": 0.04}
  ]},
  {"Name": "illustration_8", "Operations": [
    {"Op": "flat", "Variables": ["roi"], "Annual": 0.08}
  ]},
  {"Name": "fall_after_one_year", "Operations": [
    {"Op": "shock", "Variables": ["roi"], "Month": 13, "Factor": 0.7}
  ]}
]
```

```sh
uv run avk scenarios library demo-term/valuation.json demo-term/library.json demo-term/library
```

## Scenario summaries and UNIT_LINKED

The UNIT_LINKED design declares `roi`, `vroi`, `reference_forward` and ten
monthly-effective asset returns: `ret_eq_large`, `ret_eq_mid`, `ret_eq_small`,
`ret_eq_global`, `ret_gov_long`, `ret_gov_short`, `ret_corp_bond`,
`ret_money_market`, `ret_gold` and `ret_real_assets`. The deterministic baseline
reads the return columns from `ul_asset_returns` with a one-month lag. For a
risk-neutral set, use the chosen risk-free variable (such as
`reference_forward`) as `Risk_Free`, and list the asset returns to vary in
`Assets`. A supplied file includes all declared variables, including the ones
left deterministic. The worked tutorial shows how to add the optional
`Scenario_Summary` block to a multi-path Valuation, compare present values, and
enable dynamic lapse. [Stochastic UNIT_LINKED valuation](unit-linked-stochastic.md)
