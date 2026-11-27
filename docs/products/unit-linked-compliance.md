# Unit-linked compliance: reduction in yield, residual additions and benefit illustrations

The compliance layer of [UNIT_LINKED](unit-linked.md) answers three questions about a
design, without running a valuation:

1. Does a variant keep its **reduction in yield (RIY)** within the regulatory cap at
   gross returns of 4% and 8%? (`avk ul compliance`)
2. Which **residual addition** would bring a breached cap back, per policy and policy
   year? (`avk ul additions`)
3. What does a policy show in a **benefit illustration** at 4% and 8%? (`avk ul illustration`)

All three read the same run file as `avk check`: the book passes the normal input gate
first, and the caps come from `ul_riy_caps` by the variant's regime and policy year. The
numbers are projections of a single life, so they run in seconds and need no kernel build.

```powershell
uv run avk ul compliance "$HOME\avk-work\demo-ul\valuation.json" --output "$HOME\avk-work\compliance"
uv run avk ul additions "$HOME\avk-work\demo-ul\valuation.json" --output "$HOME\avk-work\compliance"
uv run avk ul illustration "$HOME\avk-work\demo-ul\valuation.json" --policy UL0000001 --output "$HOME\avk-work\compliance"
```

The Python entry points are `avk.api.ul_compliance`, `ul_residual_additions` and
`ul_illustration`; each returns the frames and the paths of the files it wrote.

## Method

**Projection.** One life is rolled through the policy term under a fixed gross return `g`
(an annual-effective rate, applied to every fund and every asset class), with no deaths,
lapses, withdrawals or switches. The roll is the per-life unit fund of the projection:
allocation charge, administration charge, mortality and guarantee charges, loyalty,
booster and guaranteed additions, rebalancing and each fund's management charge, month by
month. A test ties the two to 1e-9 for every design feature the demo variants use. The
monthly rate comes from the scenario library's `flat` operation, so it is the library's
monthly equivalent of `g`. A fund's `alpha` is an expected-return parameter, not a charge,
and is left out: the demonstration fixes the gross return itself.

**Net yield and RIY.** An instalment is invested at the start of its policy month and the
fund value is taken at the end of policy month `12n`. The net yield `y` after `n` years is
the annual-effective internal rate of return that equates the instalments paid so far
with that fund value:

    sum over instalments j of  P_j x (1 + y)^(n - t_j)  =  fund value at year n

where `t_j` is the time of instalment `j` in years from inception. The reduction in yield
is `RIY = g - y`. It is compared with `riy_max` for the policy year `n` and the variant's
regime.

**What is left out.** As the product specification requires, the RIY basis excludes the
mortality charge (with the extra mortality and flat extra loadings), the cost of any
investment guarantee, partial withdrawals and tax on charges. Return of charges and the
maturity guarantee top-up are benefits and are not part of the fund value used for the
yield. The benefit illustration keeps every charge but reports the RIY measured on this
basis.

**Measurement points.** The RIY is measured at the end of every policy year from the
fifth to the term (the last point is maturity). Years one to four of `ul_riy_caps` are not
measurement points: a regular-premium policy always breaches a cap in its first years.

## Residual additions

Where the RIY of a policy would exceed the cap, the insurer credits units so that it does
not. The first five policy years must comply by design: a breach at year five or earlier is a
design failure, whatever the variant allows. Additions are possible from the sixth
anniversary and only for a variant with `riy_additions_on = 1`.

The addition is computed in closed form, without a goal seek. The fund must reach the
accumulated value of the premiums paid so far at the target net yield `g - cap`; the
addition at the anniversary is the shortfall, never below zero:

    target fund  =  sum_j P_j x (1 + g - cap)^(n - t_j)
    addition_n   =  max(target fund - fund value_n, 0)

It is credited at the end of month `12n`, pro rata to the fund slots, so the units
credited and the cost to the general fund are the same amount. Additions are found year by
year: a later year sees the fund enlarged by earlier additions, so it needs less than its
stand-alone shortfall. The result is reported per policy and policy year by `avk ul additions`.

**Status.** Each case is given one of four statuses:

| Status | Meaning |
|---|---|
| `pass` | The RIY is within the cap at every measurement point. |
| `pass_with_additions` | The cap is breached only from policy year 6, the variant allows additions and they restore every cap. |
| `design_fail` | The cap is breached at policy year 5 (the first measurement point) or earlier: a charge design problem. |
| `fail` | A late breach that the variant does not allow additions to repair. |

A breach is an excess of RIY over the cap above 1e-12 (a rate, not a percentage).

**Status in the projection.** Residual additions are computed and reported here. They are
**not yet** a cashflow of the unit-linked projection: `residual_additions` in the general
fund is still zero. Wiring the amount into the general fund and the units is a later step.

## `avk ul compliance`: the pricing-time demonstration

For every variant in `ul_variants`, at every gross return, the command tests a grid of new
policies:

- each policy term (`--terms`, default 10, 20, 30; at least 5);
- each premium frequency (`--frequencies`, default 1 and 12); single premium variants have
  one case;
- the lowest and highest annualised premium of the book's policies of that variant
  (the whole book's when the variant has none), or `--premiums`;
- the selectable fund with the highest management charge, the binding case (or `--fund`);
- a standard life aged 35 paying premiums for the whole term.

`--rates` changes the gross returns (default 4% and 8%). `--strict` exits 1 when any case
fails; without it a failing design is a result and the exit code is 0. The command prints one
line per variant with its worst status at each gross return and writes, with `--output`:

| File | Rows |
|---|---|
| `ul_riy_cases.csv` | A case, gross return and measured policy year: net yield, RIY, cap, excess, `Within_Cap`, the addition and the RIY with it |
| `ul_riy_summary.csv` | A case and gross return: `Status`, `First_Breach_Year`, `Max_RIY`, `Worst_Margin` (cap less the highest RIY, negative on a breach), `Total_Residual_Additions` |
| `ul_riy_variants.csv` | A variant: the worst status over its cases at each gross return |

On the invented demo basis the smallest premiums of the book (about 50,000 a year) breach the
year-five cap in every regular-premium variant, because the flat monthly administration
charge is a large share of such a premium; at the largest premiums the variants pass,
`ULIP_SINGLE` passes with additions and the uncapped `UL_INVESTMENT_BOND` passes. This is a
property of the invented charges, shown so that the check can be seen working.

## `avk ul additions`

Residual additions for every premium-paying policy (`Policy Status` 0) of the book, or one
policy with `--policy`, at each gross return, from the sixth anniversary. The policy is
measured as sold, from inception, not from its fund value at the valuation date. Policies
that are discontinued or reduced paid-up are skipped and counted. `ul_residual_additions.csv`
has a row per policy, gross return and policy year: premiums paid, fund value, net yield,
RIY, cap, the addition, the RIY with the addition, and the status of the contract.

## `avk ul illustration`: the benefit illustration

One premium-paying policy as sold, by policy year, at each gross return. Every charge is
deducted and the residual additions that the RIY test needs are credited. The file is
`ul_illustration_<policy>.csv` with a row per gross return and policy year:

| Column | Meaning |
|---|---|
| `Premiums_Paid` | Premiums paid in the year |
| `Premium_Allocation_Charge`, `Administration_Charge`, `Mortality_Charge`, `Guarantee_Charge`, `Fund_Management_Charge` | Each charge deducted in the year |
| `Loyalty_Addition`, `Booster_Addition`, `Guaranteed_Addition`, `Residual_Addition` | Additions credited in the year |
| `Fund_Value` | At the end of the policy year, after the year's additions |
| `Death_Benefit` | If death occurred at the year end: Type I the higher of cover, fund and the premium floor; Type II the cover plus the fund, at least the premium floor |
| `Discontinuance_Charge`, `Surrender_Value`, `Surrender_Payable_Month` | Discontinuing at the year end. Inside the lock-in the charge is deducted and, with the Discontinued Policy Fund on, the proceeds are payable at the end of the lock-in (that month is given); otherwise the fund is paid at once. Blank in the maturity year |
| `Maturity_Value` | In the final year only: the fund, return of charges and any maturity guarantee top-up |
| `Net_Yield`, `RIY`, `RIY_Cap` | From policy year 5, on the RIY basis with the additions credited |
| `RIY_Before_Additions` | The design RIY, before any addition |

Rows are CSV only: the repository has no spreadsheet writer. Amounts are not rounded.

## Limits

- One life, fixed gross return: no decrements, policyholder options, switches, top-ups or
  lifecycle strategies. A stochastic test would be needed if a guarantee were added to the
  yield.
- The additions and the illustration use the contract as sold. They do not use the actual
  fund history of an in-force policy.
- The investment guarantee charge and the guarantee itself are outside the RIY basis.
- The IRDAI caps in the demo tables are the demo's reading of the regulations. Verify them
  before any other use.
