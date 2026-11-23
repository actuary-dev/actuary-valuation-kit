# Concepts
A **product** is a composition of formula components plus a factory. Components
define monthly columns such as deaths or premiums. The factory declares the
tables, policy fields, validation, preparation and output labels needed to run it.
Formulas are compiled once for an identity; they do not execute one Python object
per policy. Formula overrides must be explicit.

A **basis** evaluates the same product with different assumptions: `reserving`
uses prudent margins; `be` uses best estimates. A curve is an interest-rate
schedule; the loaded annual-effective rates are converted to monthly rates by
the declared assumption contract. Every product parameter is explicit.
The invented demo is a teaching basis, not a market or regulatory calibration.

A **run file** chooses valuation date, projection years, products, batch size,
input locations, output folder and run type. JSON and YAML are supported.
A logical table name separates what a product needs from the physical CSV or
Parquet file. `Inputs.Replace` changes individual locations/formats.
Configuration and input validation happen before projection.

A **case** changes shocks or input overrides around the base run and produces
a valuation-date impact table. A **stress-capital** run groups stress losses
and combines them with explicit correlation and capital-cost settings.
The optional factor-based solvency-capital columns in valuation are a separate
measure; do not interpret them as the combined stress result.

**IFRS 17** GMM measurement uses grouped contracts, cohort locked-in curves,
current BEL and risk adjustment (RA), recognition CSM and loss components.
BEL is best-estimate liability, CSM is contractual service margin.
A roll-forward adds opening balances and inventories to explain a reporting
period's movements. It does not produce a full revenue/expense accounting statement.
RA may use an explicit claims ratio or a stress cost-of-capital basis.

Outputs have different levels: aggregate rows by projection step; seriatim rows
by policy at selected steps; optional detailed policy-month cashflows; group
and roll-forward reporting tables. Use the [output conventions](output-conventions.md)
and [column reference](reference/output-columns.md) to select the correct measure.
`run_record.json`, logs and status preserve the run's inputs and execution details.
