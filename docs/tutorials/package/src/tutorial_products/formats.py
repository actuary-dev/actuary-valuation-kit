"""An alternative wide mortality format with the usual probability validation."""

import numpy as np

from avk.inputs.formats import integer_axis, key_axis, numeric, table


def mortality(frame, spec):
    frame = frame.sort("age")
    ages = frame["age"].to_numpy()
    if len(ages) == 0 or not np.array_equal(ages, np.arange(ages[0], ages[-1] + 1)):
        raise ValueError("ages must be consecutive and unique")
    renamed = frame.rename(dict(zip(("m", "f", "x"), spec.columns, strict=True)))
    return table(
        spec,
        numeric(renamed, spec.columns, spec),
        (
            integer_axis("age", int(ages[0]), len(ages), spec.axes[0]),
            key_axis("sex", tuple(range(len(spec.columns)))),
        ),
    )
