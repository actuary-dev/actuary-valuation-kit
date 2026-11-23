# Reading outputs correctly
Use the run record to identify product, basis, valuation date, cases and inputs.
Amounts are in the input currency; rates and proportions are fractions.
The invented demo is not a recommended commercial basis.
The [column reference](reference/output-columns.md) names each source and basis.

## Dates and opening reserves
Projection step 0 is the internal valuation instant. Step **1** is the reported
valuation-date row. A projection-step number is not a policy duration: policies
start on different dates. Select step 1 when reading a valuation-date total.
Valuation and stress-capital runs retain the net reserve at the internal instant;
IFRS 17 masks that opening reserve. Product-specific reserve floors still apply.

The held reserve is **cashflows_be_reserves_BE**, a book amount net of reinsurance,
on best-estimate eligible lives. Do not substitute a gross reserve, a per-survivor
ratio or the similarly named MCEV BEL. MCEV BEL is a present-value cashflow measure;
its sign need not match a positive liability balance. IFRS17_bel_current uses the
IFRS measurement convention: claims and expenses less premiums. Held-reinsurance
BEL uses premiums paid less recoveries received. Keep these sign conventions
when interpreting impacts and adding held reinsurance.

## Book ratios and missing values
The aggregate reserve/BEL columns ending in *_pp* are **book ratios**: the sum
of the relevant held numerator divided by the sum of its eligible lives.
They are not sums or unweighted averages of policy ratios.
The generated reference lists each numerator, denominator, basis and sign.
For example, amounts 200 and 600 with eligible lives 1 and 3 give 800 / 4 = 200,
not 200 + 200 = 400. Gross/net reserve numerators include the product reserve floors.
MCEV BEL-per-policy uses the negative of the exported BEL numerator;
IFRS BEL-per-policy uses its declared positive sign.

Eligibility follows the product's reserve-lives measure, including maturing lives
where declared; it is not automatically the closing-life column. A zero
denominator can give an undefined ratio, exported blank/NaN. Do not fill that
with zero and then average ratios. Read amount totals and valid denominators.
A seriatim file selects particular steps per column; it is not a duplicate
of every aggregate step.

## Expense schedules
IFRS initial expenses multiply the best-estimate initial expense by the specified
IFRS multiplier. Commission appears once, in renewal expenses. Where the shared
fixed-expense schedule applies, the annual amount is charged on policy months
1, 13, 25 and so on, per life in force at the opening of the month. Each death
attracts the claim-expense rate for its policy year. Unstressed commission enters
both the base and the stressed renewal-expense amounts, so it cancels in expense
capital. In IFRS 17 measurement, acquisition expenses are discounted from the
start of each month on the locked-in curve.

For frequent-payer IFRS premium-related expenses, the preceding nonzero schedule
rate carries across a zero pulse. A rate of 0.015 followed by zero therefore
continues at 0.015 in that carry path. A schedule lookup outside the horizon
returns zero, but the carried rate can remain nonzero. Do not interpret every
zero schedule entry as cancelling the carried expense.

Initial-expense rates use linear interpolation and clamp beyond the end knots.
Term and riders index by sum assured; credit life indexes by outstanding loan.
For invented knots 100 and 300 with rates 0.01 and 0.03, an index of 150 gives
0.015; an index of 400 clamps to 0.03.

Expense shocks change the declared expense components, including supported IFRS
schedules, and exclude commission. For commission of 10% on a premium of 100,
a 10% expense stress leaves commission at 10. A commission change requires an
explicit table/parameter override.

## Discount curves and policy timing
Rider frictional cost of capital (FCC) uses the valuation reference forward curve.
Term and credit life use the IFRS reference curve at the policy's own month offset.
FCC here means frictional cost of capital; it is distinct from IFRS fulfilment cashflows.

Term and credit life count calendar months. Riders subtract one month when the
valuation day precedes the issue day; the internal duration also includes its
declared starting-month offset. Future policy durations can be negative.
For an issue on 18 August 2025 and valuation on 15 June 2026, the calendar
difference is 10 months. The prepared Term duration is 11 and the rider duration
is 10: both include the starting-month offset, and the rider subtracts one
because 15 is before 18. The formula then adds the projection step to that
duration. This can move anniversary and maturity events.

Riders retain their own inception/in-force masks. Ordinary lapses become eligible
only after policy month 1, and still need a due month. Death eligibility is a
separate rule. Do not impose Term masks on rider results when reconciling exits.

The onerous test discounts each policy on its own IFRS reference forward curve.
The curve holds its final rate flat when the policy runs beyond the supplied term.

## Mortality, premiums and reinsurance
Annual mortality is capped at 100% before conversion to a monthly probability.
Term reinsurance mortality uses its own table. Term mortality loading bands
start at their lower bound and extend up to the next band's lower bound. The
last band stays open, and an amount below the first band fails validation.
Credit-life and rider mortality
are zero before inception. Rider settlement expenses follow the insured event,
such as accidental death or critical illness incidence. Accidental death
reinsurance uses the sum assured and excludes waiver benefits.

Term and rider premiums, including the rider base premium eligible for waiver,
stop at the premium payment term. Credit life's single premium falls in policy
month 1, which can coincide with the internal valuation instant.

## Cession and credit-life expense timing
Month-1 reinsurance cession uses the valuation-instant ceding reserve, including
future-start policies. That reserve is separate from the reported gross opening
reserve's mask. A zero reported gross opening reserve therefore does not imply
a zero reserve in the cession calculation.

Reducing credit-life cover starts from outstanding principal. Where interest
applies, it starts at loan inception. Payments resume after the remaining holiday. Initial
expense rates are selected using the month-one sum assured after the timing shift.
The unearned premium reserve floor uses first-projection-month commission before
decrement weighting. The reported credit-life IFRS BEL is shifted to the same
reporting time as the Term and rider values.

Credit-life IFRS fixed expense charges the year-one annual schedule at step 1.
From step 2 it uses the monthly carried schedule. Steps 0 and 1 are undecremented;
later fixed expenses use opening best-estimate lives. For an invented annual
schedule of 24, step 1 starts with 24 before applicable shocks/inflation;
the monthly base thereafter is 2, with the appropriate lives weighting.
This is a distinct credit-life convention, not the shared anniversary rule.

## Capital and IFRS group tables
Stress-capital output combines labelled stresses under the run's chosen method,
correlation, floor, operational risk and cost loading. The pv_cost_of_capital
column is a present value of future holding costs. Factor-based solvency-capital
columns in valuation are a different measure.

IFRS groups separate portfolio, cohort and profitability. Direct CSM, direct
loss component, held CSM and loss recovery have distinct meanings; preserve
them separately. In the roll-forward, positive release amounts are subtracted
from the corresponding balance. Held CSM includes loss recovery, so its
future-service movement includes the change in loss recovery along with the change
in held fulfilment cash flows. CSM releases follow coverage units. The loss and
loss-recovery releases follow expected outflows and released risk adjustment.
The six-month demo uses explicit opening
balances and inventories; it does not derive all opening balances from a
valuation aggregate. The notebooks show the available bridge, not a full
insurance revenue/expense statement.
