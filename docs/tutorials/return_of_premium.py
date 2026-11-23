"""Add return of premium without changing the engine."""

import sys

import polars as pl
from worked import inputs, project, same_outputs, setup, verify

folder = setup(sys.argv[1])
cfg = inputs(folder, annual_mortality=0.0)
baseline = project(folder, cfg, "TUTORIAL_TERM", "plain-term")
frame = project(folder, cfg, "TUTORIAL_ROP", "return-term")
verify(frame, annual_mortality=0.0)
refund = frame.filter(pl.col("Projection_Step") == 23)["returned_premiums_BE"][0]
assert refund == 200.0
assert frame["returned_premiums_BE"].sum() == 200.0
column = "cashflows_net_cashflows_reserving"
expected = baseline.with_columns(
    (pl.col(column) + 200.0 * (pl.col("Projection_Step") == 23)).alias(column)
)
same_outputs(
    frame.select("Projection_Step", column),
    expected.select("Projection_Step", column),
)
print("PASS: maturity at step 23; returned premiums = 100 x 2 x 1 = 200.00")
