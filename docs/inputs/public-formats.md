# Public table formats, version 1

A format is selected explicitly by an input's Format. Built-in names below use
the same resolver as installed entry points in the avk.formats group.
Each reader takes (Polars DataFrame, FormatSpec) and returns a numeric Table.
Installed names cannot collide with built-in names. Only a selected plug-in loads.
Old readers remain available during the transition.

CSV columns are exact and case-sensitive. Numbers are unadorned decimal numbers,
never percentages or numbers containing separators. Null, NaN, infinity, Boolean
numbers, duplicate keys and incomplete grids fail. No missing value becomes zero.
Probabilities are fractions in [0, 1]; annual effective interest must exceed -1.
Rows may be reordered. Fields use lower case words joined by underscores; the
reader maps these public names to the binding's declared value columns.

| Assumption | Format | Columns | Keys and rules |
|---|---|---|---|
| Mortality | avk_mortality_v1 | age,field,value | Consecutive nonnegative integer ages; one value per required field and age |
| Morbidity | avk_morbidity_v1 | age,field,value | Same grid; required fields selected by product |
| Lapse | avk_lapse_v1 | year,channel,value | Integer years from 1; nonnegative integer channels; complete rectangle |
| Expenses | avk_expenses_v1 | section,index,field,value | initial: sum-assured knots; renewal: index 0; schedule: annual years from 1 |
| Commission | avk_commission_v1 | year,channel,value | Same rectangle and probability rules as lapse |
| Curves | avk_curves_v1 | year,field,value | Integer projection years from 1; enough years for horizon |
| Product parameters | avk_parameters_v1 | product,parameter,value | Unique product/parameter; parameter is the definition's exact required name |
| Stress sets | avk_stresses_v1 | risk,target,method,additive,multiplier,start_month,end_month,maximum_decrease,factor | Disjoint windows per risk/target; all numeric controls explicit |
| Correlations | avk_correlations_v1 | risk,other,value | Complete square, unit diagonal, symmetric, positive semidefinite, values in [-1,1] |
| Opening IFRS 17 balances | avk_opening_v1 | product,portfolio,cohort,profitability,csm,loss_component,ri_csm,loss_recovery_component | Unique group; all amounts explicit; only ri_csm may be negative |
| Unit-linked keyed tables | avk_ul_keyed_v1 | key,field,value | Exact string keys (no trimming or case folding); the file holds exactly the declared fields; one value per key and field |
| Unit-linked year tables | avk_ul_year_key_v1 | year,key,field,value | Integer years from 1; nonnegative integer keys; complete year/key rectangle for each field a binding selects |

Mortality fields: male, female, transgender (the third field is required by the
engine's current three-column mortality contract). Morbidity fields:
accidental_death_male/female, critical_illness_male/female,
disability_rider_male/female. A shared file may include fields for several
products; every required field must exist at every key. Credit Life support
loadings use the mortality layout with fields re_m_ns, re_m_s, re_f_ns, re_f_s,
be_m_ns, be_m_s, be_f_ns, be_f_s. Those bindings declare nonnegative factors,
which may exceed 1, rather than probabilities.

Expense initial fields: sa, of_prem, fixed, of_sa. The sa value equals index;
the other values interpolate linearly across knots and clamp outside them.
Renewal and schedule fields: fixed_expenses, claim_expenses, of_prem.
Fixed amounts are annual currency units; other values are fractions.
Schedules need every projection year. All expense values are nonnegative.

Curve fields: roi, vroi, reference_forward_rates; the IFRS curve has
if17_current_roi, if17_locked_in_rate, if17_reference_forward_rates.
Scenario timing and monthly-effective conversion are declared by the product,
not encoded as shifted rows in the file.

Stress methods: revaluation, mass_lapse, catastrophe. The last two use target
none, an explicit factor, and neutral controls 0,1,0,0,1. Revaluation factor is
zero. Window 0,0 means the whole run; otherwise both months are positive integers
within the projection. Only lapse uses maximum_decrease other than 1. Multiple
targets may share a risk (for example expense and inflation).
A run selects stress rows with:
Cases: {CSV: stresses.csv, Format: avk_stresses_v1} inside Stress_Set.
Correlation uses {CSV: correlations.csv, Format: avk_correlations_v1}.
Capital settings remain explicit in the run file; these tables supply no defaults.

Opening direct CSM and loss component cannot both be positive. Loss recovery
cannot exceed direct loss. Existing roll-forward validation additionally checks
the exact opening groups, the two reporting dates and the closing book.

Two supplementary preparation tables use public layouts:
avk_bands_v1: lower,upper,smoker,value; lower >= 0, upper > lower,
smoker 0 or 1; sorted by smoker and lower before preparation.
avk_frequencies_v1: frequency,field,value; positive integer frequencies,
positive modal factors, one field for each product. Neither reader inserts a
missing category.

The same avk_curves_v1 format supports cohort curves with columns
cohort,month,value, where month is YYYY-MM and value is monthly effective.
Cohort/month keys must be unique; missing months required by a measurement run
are rejected by the measurement gate. Each number is finite and greater than -1.

Stress windows are inclusive projection-month intervals. A pair of zeroes means
the whole run. Several rows may share a risk and target only when their windows
are disjoint; duplicate or overlapping intervals fail clearly. Explicit final
month is Projection_Term*12-1, matching native End_Month: last. Rows for a target
become the existing list-of-shocks representation; no model formula changes.

Unit-linked tables. avk_ul_keyed_v1 serves ul_funds (key Fund Code),
ul_variants (key Product Variant) and ul_regulatory_caps (key regime code). Keys
sort as strings; a key with a trailing space is a different key. avk_ul_year_key_v1
serves ul_charge_scales (key variant_id), ul_disc_charge_caps and ul_riy_caps (key
regime_id); each binding reads one field, so one file holds several fields. The
fields of every table are listed in [the unit-linked product page](../products/unit-linked.md).
