"""Select an installed format hook and prove complete product output equality."""

import sys

import polars as pl
from worked import inputs, project, same_outputs, setup

from avk.inputs.formats import FormatSpec, key_axis, read
from avk.model.data import Axis

folder = setup(sys.argv[1])
# Keep the generated age- and sex-varying public mortality probabilities.
cfg = inputs(folder, annual_mortality=None)
policy = pl.read_csv(folder / "policies.csv")
pl.concat(
    [
        policy.with_columns(
            pl.lit(number).alias("Policy Number"),
            pl.lit(sex).alias("Gender"),
            pl.lit(age).alias("Age at Policy Start"),
            pl.lit(cover).alias("Sum Assured"),
        )
        for number, sex, age, cover in (
            ("DEMO-M", "M", 35, 1000.0),
            ("DEMO-F", "F", 45, 2000.0),
        )
    ]
).write_csv(folder / "policies.csv")
expected = project(folder, cfg, "TUTORIAL_TERM", "normal-format")
path = folder / "wide-mortality.csv"
public = pl.read_csv(folder / "basis" / "mortality.csv")
wide = (
    public.pivot(on="field", index="age", values="value")
    .select("age", "male", "female", "transgender")
    .rename({"male": "m", "female": "f", "transgender": "x"})
    .sort("age")
)
wide.write_csv(path)
cfg["Inputs"]["Replace"]["mortality"] = {
    "Path": str(path),
    "Format": "tutorial_mortality",
}
actual = project(folder, cfg, "TUTORIAL_TERM", "wide-format")
same_outputs(actual, expected)
print(
    f"Future premiums = {actual['cashflows_be_premiums_BE'].sum():.8f}; "
    f"death benefits = {actual['cashflows_be_death_benefits_BE'].sum():.8f}; "
    f"step 1 lives = "
    f"{actual.filter(pl.col('Projection_Step') == 1)['decrements_lives_so_end_BE'][0]:.12f}"
)
# Term accepts only M/F policies. Also exercise all three reader columns and
# every age through the public format boundary, including the unused x column.
spec = FormatSpec(
    "mortality",
    {},
    (
        Axis("age", "int", 0, 121, "error", "clamp", (), None),
        key_axis("sex", (0, 1, 2)),
    ),
    ("male", "female", "transgender"),
    "TUTORIAL_TERM",
    24,
    "probability",
)
normal_table = read("avk_mortality_v1", public, spec)
wide_table = read("tutorial_mortality", pl.read_csv(path), spec)
assert wide_table.axes == normal_table.axes
rate_columns = ("male_rate", "female_rate", "transgender_rate")
same_outputs(
    pl.DataFrame(wide_table.values, schema=rate_columns, orient="row"),
    pl.DataFrame(normal_table.values, schema=rate_columns, orient="row"),
)
print("PASS: wide mortality hook preserves every aggregate column")
