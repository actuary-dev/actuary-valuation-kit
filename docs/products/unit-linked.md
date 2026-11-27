# Unit-linked insurance (UNIT_LINKED)

UNIT_LINKED values unit-linked life insurance: premiums, less charges, buy units in
one or more funds; the policyholder carries the investment risk; cover and other
charges are met by cancelling units. One compiled product covers regular, limited
and single premium designs. Data switches design features on and off: the death
benefit type, the lock-in and Discontinued Policy Fund (DPF), reduced paid-up,
partial withdrawals, loyalty and booster additions, return of charges, a maturity
guarantee and regulatory caps.

**Status.** Phase P2a adds the unit projection on all three bases. Valuation reports
lives by state, premiums, unit funds and charges, and the unit and general-fund
shares of benefits. The Discontinued Policy Fund and reduced paid-up state each
pool expected balances and lives into a single cohort per policy. General-fund
expenses, reserves, profit, capital and MCEV are phase P2b.

Phase P3 adds the [compliance layer](unit-linked-compliance.md): the reduction in yield
against `ul_riy_caps`, the residual additions that would restore a breached cap, a
pricing-time demonstration for every variant at 4% and 8%, and the benefit illustration
(`avk ul compliance`, `avk ul additions`, `avk ul illustration`). Residual additions are
not yet a cashflow of the projection.

Run the invented demo:

```powershell
uv run avk demo generate "$HOME\avk-work\demo-ul" --product UNIT_LINKED --count 10000 --seed 209
uv run avk check "$HOME\avk-work\demo-ul\valuation.json"
uv run avk run "$HOME\avk-work\demo-ul\valuation.json"
```

UNIT_LINKED supports the Valuation run type only; StressCapital and IFRS17 are
rejected with `UNIT_LINKED supports the Valuation run type only`. It has three bases:
`reserving`, `be` (best estimate) and `mc` (market consistent).

## Timing conventions

Policies mature in the final month of their term. A policy whose term ends in the
valuation month matures at the valuation date, and step 0 holds its maturity value
in the unit reserve.
The policy settles in projection month 1 from those balances, with the applicable
return of charges and maturity guarantee. No premiums, charges, investment returns,
decrements, rebalancing or additions apply in that settlement month.

The Discontinued Policy Fund (DPF) releases at the earlier of lock-in end and term
end. A balance already due at valuation is paid in projection month 1. An
anniversary addition requires either a positive fund balance after deductions or
positive allocation weights. Without either, both the unit credit and the
general-fund cost are zero.

## Policy table `policies_ul`

One row per policy. Every column is required and no value may be missing; nothing
defaults. Dates are `YYYY-MM-DD` (or the other layouts the policy readers accept).

| Column | Type | Meaning and rules |
|---|---|---|
| Policy Number | text | Unique |
| Product Code | text | `UNIT_LINKED` |
| Product Variant | text | A key of `ul_variants` (exact match) |
| Valuation Date | date | Equal to the run's valuation date |
| Policy Start Date | date | On or before the valuation date |
| Policy Term (Years) | integer | Positive. The valuation date may fall in the final month of the term. |
| Premium Payment Term (Years) | integer | 0 for single premium; at most the term |
| Premium Frequency | code | 0 single, 1, 2, 4 or 12; 0 if and only if the payment term is 0 and the variant is single premium |
| Annualised Premium | amount | The single premium for single-premium policies |
| Sum Assured | amount | At least the regime's minimum cover multiple of the premium for the entry age (when the regime applies caps) |
| Distribution Channel | integer | A channel of the lapse, withdrawal and commission tables |
| Currency | text | One currency per run |
| Date of Birth | date | |
| Age at Policy Start | integer | Completed years from Date of Birth to Policy Start Date |
| Gender | code | M, F or T |
| Smoking Status | code | NS or S |
| Underwriting Class | integer | Nonnegative (not read yet) |
| EMR | number | Extra mortality multiple, positive; 1 standard |
| Flat Extra | amount | Per mille of sum at risk a year |
| Flat Extra Term (Years) | integer | |
| Policy Status | code | 0 premium paying or fully paid, 1 discontinued in the DPF, 2 reduced paid-up |
| Status Date | date | The date the current status began; Policy Start Date <= Status Date <= valuation date |
| Paid Up Sum Assured | amount | Positive if and only if Policy Status is 2 |
| Date Of Last Premium Paid | date | History (not read yet) |

History to date, for retrospective calculations (amounts, nonnegative): Premiums Paid
To Date (at least the sum of Premiums Allocated To Fund over the policy's holdings),
Instalments Paid (integer), Premium Allocation Charges To Date, Policy Administration
Charges To Date, Mortality Charges To Date, Guarantee Charges To Date, Loyalty
Additions To Date, Partial Withdrawals To Date, Withdrawals Current Policy Year,
Withdrawals Previous Policy Year, Fund Value Sum Current Policy Year (sum of
month-end fund values since the last anniversary), Discontinuance Charge Paid.

IFRS 17 grouping (not read yet): Portfolio (text), Issue Cohort (year), Profitability
Group (0 onerous at recognition, 1 no significant possibility of becoming onerous,
2 other), Transition Approach (0 full retrospective, 1 modified retrospective, 2 fair
value), Measurement Model (VFA or GMM), Legal Entity (text).

## Fund holdings table `policy_funds_ul`

One row per policy and fund held: a companion table of the policy table, read once
per run and joined to each batch of policies. Every column is required.

| Column | Meaning and rules |
|---|---|
| Policy Number | A policy of `policies_ul`; Policy Number + Fund Code is unique |
| Product Code | Equal to the policy's |
| Fund Code | A key of `ul_funds`, matched exactly (no trimming or case folding) |
| Valuation Date | Equal to the policy's |
| Units | Nonnegative; fund value = Units x unit price |
| Premium Allocation | Fraction of future premiums in [0, 1]; 0 for non-selectable funds; a premium-paying policy (status 0 within its payment term) sums to 1 within 1e-9 |
| Fund Entry Date | On or before the valuation date |
| Premiums Allocated To Fund, Units Allocated To Date, Units Cancelled To Date, Switches In To Date, Switches Out To Date | History, nonnegative (not read yet) |
| Guaranteed Unit Price | Highest NAV recorded for a guaranteed fund, else 0 (not read yet) |

Every policy holds at least one row. A policy holds at most `MAX_FUND_SLOTS` (5)
funds outside the DPF. A status-1 policy holds exactly one row, in the DPF; other
policies hold none in the DPF. A holding whose policy is in no batch of the policy
table is reported once, after every batch has been read.

## Fund universe `ul_funds`

Format `avk_ul_keyed_v1` (key = Fund Code). Fields:

| Field | Rule | Meaning |
|---|---|---|
| unit_price | > 0 | Unit price at the valuation date |
| fmc | [0, 1) | Annual fund management charge |
| alpha | > -1 | Annual return over the asset mix (negative for tracking cost) |
| w_eq_large ... w_real_assets | [0, 1], sum 1 within 1e-12 | Asset mix over the ten asset classes |
| selectable | 0 or 1 | 1 the fund may receive premiums |
| is_dpf | 0 or 1 | Exactly one fund has 1, and it has selectable 0 |
| guarantee_type | 0, 1, 2 | 0 none, 1 highest NAV, 2 capital protection (mechanics in a later phase) |
| risk_class | 1 to 5 | |

Asset classes: eq_large, eq_mid, eq_small, eq_global, gov_long, gov_short,
corp_bond, money_market, gold, real_assets. The demo universe has 22 invented funds:
nine equity, four hybrid, three debt, a liquid fund, gold, real assets, two
guaranteed funds and the DPF.

## Variants `ul_variants`

Format `avk_ul_keyed_v1` (key = Product Variant). Every field is required:

| Field | Allowed | Meaning |
|---|---|---|
| variant_id | integer >= 0, unique | Key of `ul_charge_scales` |
| regime_id | integer | A regime of `ul_regulatory_caps` |
| single_premium | 0, 1 | 1 single premium; limited pay is a payment term below the term |
| death_benefit_type | 1, 2 | 1 Type I (higher of cover and fund), 2 Type II (cover plus fund) |
| min_db_premium_multiple | >= 0 | Death benefit floor as a multiple of premiums paid |
| lock_in_months | integer >= 0 | Discontinuance inside the lock-in goes to the DPF |
| dpf_enabled | 0, 1 | |
| rpu_mode | 0, 1, 2 | Cessation after the lock-in: 0 pays out, 1 paid-up to maturity, 2 paid-up until the end of the revival period |
| revival_period_months | integer >= 1 | |
| pw_allowed, pw_start_year, pw_reduces_sa | 0/1, integer >= 1, 0/1 | Partial withdrawals; withdrawals of the current and previous policy year reduce cover when pw_reduces_sa is 1 |
| loyalty_on, loyalty_basis, loyalty_start_year, loyalty_requires_full_premiums | 0/1, 1 or 2, integer >= 1, 0/1 | Loyalty additions on the average month-end fund (1) or the annualised premium (2) |
| guaranteed_addition_rate | [0, 1] | Of the annualised premium, each policy year |
| romc_fraction, ropac_fraction, roadmin_fraction | [0, 1] | Mortality, allocation and administration charges returned at maturity |
| gmmb_on, gmmb_premium_multiple, guarantee_charge | 0/1, >= 0, [0, 1) | Maturity guarantee and its annual charge |
| admin_escalation | [0, 1) | Annual escalation of the administration charge |
| mortality_charge_multiplier | >= 0 | Applied to `mortality_charges_ul` |
| disc_ap_threshold | >= 0 | Annualised premium above which the high discontinuance scale applies |
| auto_rebalance | 0, 1 | Rebalance to the premium allocation each anniversary |
| riy_additions_on | 0, 1 | Reduction-in-yield residual additions: allowed from policy year 6 ([compliance](unit-linked-compliance.md)) |

## Charge scales and regulatory caps

`ul_charge_scales` (format `avk_ul_year_key_v1`, key = variant_id, policy years from
1): premium_allocation_rate, admin_charge_monthly, loyalty_rate, booster_rate,
disc_pct_low, disc_cap_low, disc_pct_high, disc_cap_high. Every variant_id has a
scale and every scale key is a variant_id.

`ul_regulatory_caps` (format `avk_ul_keyed_v1`, key = regime code): regime_id,
caps_apply, pac_max, pac_ratio_max_first5, admin_max_monthly, admin_escalation_max,
fmc_max, dpf_fmc_max, guarantee_charge_max, min_db_premium_multiple,
lock_in_months_min, dpf_min_rate, min_sa_multiple_regular_young,
min_sa_multiple_regular_old, regular_age_threshold, min_sa_multiple_single_young,
min_sa_multiple_single_old, single_age_threshold, switch_charge_max, pw_charge_max,
misc_charge_max. `ul_disc_charge_caps` (disc_pct_low, disc_cap_low, disc_pct_high,
disc_cap_high) and `ul_riy_caps` (riy_max) are keyed by regime_id and policy year.

When a variant's regime has caps_apply 1, `avk check` rejects (never clamps): an
allocation rate above pac_max; a first-five-year highest/lowest allocation ratio
above pac_ratio_max_first5 (a zero year fails the ratio unless all five are zero);
an administration charge above admin_max_monthly; admin_escalation above
admin_escalation_max; guarantee_charge above guarantee_charge_max;
min_db_premium_multiple or lock_in_months below the regime minimum; a discontinuance
scale above `ul_disc_charge_caps` in any year; a held fund whose FMC exceeds fmc_max
(the DPF: dpf_fmc_max); and a sum assured below the regime's minimum cover multiple.
For a capped variant that can transfer to the DPF, the DPF FMC is checked before
projection even when the book starts with no DPF holdings.
The regime `UNCAPPED` sets caps_apply 0 and explicit non-binding values, so none of
these checks applies.

The demo regime `IRDAI_2024` holds the caps of the Indian 2024 regulations as read
for this teaching example. Verify them against the regulation before any other use,
in particular the single-premium cover multiples (1.25 below age 45, 1.10 from 45).

## Rates, parameters and market variables

- `mortality` (shared experience table) and `mortality_charges_ul` (contractual
  charges per 1,000 of sum at risk by age; fields male_non_smoker, male_smoker,
  female_non_smoker, female_smoker, transgender_non_smoker, transgender_smoker).
- `lapse_rates_ul`, `partial_withdrawals_ul` and `commissions_ul`: annual rates by
  policy year and channel.
- `product_parameters`, column UNIT_LINKED: Inflation, Tax Rate, profit_transfer_rate,
  prudent margins (mortality, lapse, partial withdrawal, expense), fund_return_margin,
  experience_mortality_pct, smoker_mortality_loading, surrender_share, initial,
  renewal, claim and fund expenses, reserve_floor_days, revival strains, capital
  factors with and without guarantee, target_capital_ratio, cost_of_capital_rate and
  mc_fund_return_source.
- Scenario variables: roi, vroi and reference_forward from `interest_rates` (as Term),
  and ten monthly asset-class returns `ret_eq_large` ... `ret_real_assets` from
  `ul_asset_returns` (annual expected returns by year, one field per asset class). A
  deterministic run converts each to a monthly effective rate, lagged one month. A
  supplied scenario set carries exactly these columns.

Fund returns (phase P2a): on the best-estimate basis fund k grows at its asset-mix
weighted sum of the asset-class returns plus its monthly alpha; the reserving basis
adds the signed fund return margin; the market-consistent basis uses
reference_forward for every fund when mc_fund_return_source is 0 (certainty
equivalent) and the best-estimate formula when it is 1 (for risk-neutral sets).

## Model points

Preparation (vectorised) produces the fields the formulas read: the policy fields
(for example Duration_in_Months, Charge_Column = 2 x Gender_Code + Smoker_Code,
Instalment_Premium, Instalments_Payable and the history fields), `V_<field>` for each
variant feature, R_dpf_min_rate, R_dpf_fmc_max and R_caps_apply from the regime, the
DPF holding (DPF_Value, DPF_FMC, DPF_Alpha, `DPF_W_<asset>`) and five fund slots
`Fund_k_*` (Present, Fund_Index, Allocation, Value, FMC, Alpha, `W_<asset>`,
Premiums_Allocated, Guaranteed_Price). Slots are filled in the order of the funds'
positions in `ul_funds` keys; empty slots hold zeros and Fund_Index -1.

## Not modelled

Planned later: switching
behaviour, top-ups, lifecycle and systematic transfer strategies, premium funding
benefit, highest-NAV guarantee mechanics, settlement options, pension variants, tax
on charges and reinsurance.
