# Nested analysis settings
The [generated run-file schema](run-file.md) covers top-level keys.
Nested case, stress and IFRS settings are validated by the run layer rather
than a standalone schema class. This page describes those contracts.
Generate a public book for complete runnable examples of every run type.

## Cases
Cases is a list of mappings, or a mapping with one CSV path under CSV.
Each case needs a distinct Name. Optional Shocks maps mortality, morbidity,
lapse, expense, inflation or interest to shock settings.
At least Additive or Multiplicative is needed; omitted addition is 0 and
omitted multiplier is 1. Both supplied window bounds Start_Month and End_Month
are inclusive projection months, from 1 through the final step.
End_Month may be "last". Without bounds the shock covers the run.
Lapse alone accepts Maximum_Decrease, a fraction in [0,1], default 1.
Mortality, morbidity, lapse and expense may use lists of nonoverlapping windows.
Inflation windows stop further shocked growth at the end, retaining the
accumulated change in the price level.

Optional Mass_Lapse is a fraction; optional Overrides changes inputs first:

| Overrides key | Value |
|---|---|
| Tables | Logical table name to path or input location |
| Parameters | Product code to parameter-name/value mapping |
| Curves | Declared curve logical name to path or location |
| Valuation_Date | Date, using the run-file date parser |
| Policy_Data | Each policy-table logical name to path or location |

Unused/unknown names are rejected. CSV cases use columns such as
mortality.Multiplicative, lapse.Start_Month, lapse.End_Month,
Overrides.Tables.mortality or Overrides.Parameters.TERM.Inflation.
Blank cells are unset. Run_Type Sensitivities requires Cases.

## Stress_Set
A StressCapital run needs Stress_Set and excludes ordinary Cases.
Stress_Set is a file path or a mapping containing Cases and optionally
Correlation and Settings. A native case declares Name, Risk and Shocks;
Method defaults to revaluation for ordinary risks. Analytic mass_lapse and
catastrophe methods instead use Factor in [0,1], without input overrides/shocks.
Risk labels identify output columns. Lapse up, lapse down and mass lapse
derive a lapse maximum; the plain risk label "lapse" is reserved.

Cases can instead select a public table with CSV and Format.
Correlation accepts a labelled matrix, CSV path, or CSV/Format location.
Combined capital needs exact matching labels, unit diagonal, symmetry,
coefficients in [-1,1] and a positive-semidefinite matrix.

| Settings key | Meaning |
|---|---|
| Aggregation | policy or portfolio; default portfolio |
| Cost_of_Capital_Rate | Required nonnegative annual rate for combined capital |
| Discount_Curve | Required scenario name or Table.Column |
| Diversification_Floor | Fraction [0,1], default 0 (disabled) |
| Cost_Loading | Nonnegative multiplier, default 1 |
| Operational_Risk | Optional Premium_Charge and BEL_Charge, both nonnegative |

Correlation is required when combined-capital settings are supplied.
The generated public capital JSON and cited stress presets are complete examples.
These run-setting defaults do not supply missing assumption values.

## IFRS17
Use Run_Type IFRS17. Required settings are Reporting_Months (integer 1..120),
Locked_In_Curves (logical table), Current_Curve (scenario/curve name),
Profitability_Field (policy column), RA_Method and signed RI_RA_Ratio.
Optional Portfolio_Field and Cohort_Field select grouping columns; otherwise
the product code and issue-year cohort provide those labels.
RA_Method ratio requires nonnegative RA_Ratio and excludes Stress_Set.
RA_Method cost_of_capital requires Stress_Set and excludes RA_Ratio.
Locked-in curves must cover each cohort and required calendar month.
The group profitability values are "onerous" and "other".

Optional Roll_Forward contains exactly Opening and Opening_Balances.
Opening uses the override keys above and requires Valuation_Date plus each
opening Policy_Data source. Opening_Balances names a logical group-balance table.
The run file itself supplies closing date, inventories and assumptions.
No additional Cases can be combined with a roll-forward.
See the [roll-forward notebook](../../notebooks/rollforward.ipynb)
and [public opening-balance format](../inputs/public-formats.md).
