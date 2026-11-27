"""Unit-linked public formats: keyed and year-key tables."""

import numpy as np
import polars as pl
import pytest

from avk.inputs.formats import FormatSpec, read
from avk.inputs.registry import BUILTIN_FORMATS
from avk.model.data import Axis
from avk.runtime.errors import InputError

RULE = Axis("binding", "int", 0, 0, "error", "error", (), None)


def spec(columns, name="t"):
    return FormatSpec(name, {"path": name}, (RULE,), columns, "UNIT_LINKED", 12, "mixed")


def keyed_frame():
    return pl.DataFrame(
        {
            "key": ["B", "A", "B", "A"],
            "field": ["x", "x", "y", "y"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )


def test_keyed_round_trips_sorted_keys():
    table = read("avk_ul_keyed_v1", keyed_frame(), spec(("x", "y")))
    assert table.axes[0].name == "key" and table.axes[0].keys == ("A", "B")
    assert table.axes[1].name == "field" and table.axes[1].keys == ("x", "y")
    np.testing.assert_array_equal(table.values, [[2.0, 4.0], [1.0, 3.0]])


def test_keyed_selects_declared_field_order():
    table = read("avk_ul_keyed_v1", keyed_frame(), spec(("y", "x")))
    np.testing.assert_array_equal(table.values, [[4.0, 2.0], [3.0, 1.0]])


@pytest.mark.parametrize(
    ("frame", "fragment"),
    [
        (pl.concat([keyed_frame(), keyed_frame().head(1)]), "duplicate keys"),
        (keyed_frame().tail(3), "missing key/field combination"),
        (
            pl.concat(
                [keyed_frame(), pl.DataFrame({"key": ["A"], "field": ["z"], "value": [0.0]})]
            ),
            "unknown field(s) ['z']",
        ),
        (keyed_frame().with_columns(pl.lit(float("inf")).alias("value")), "finite"),
        (keyed_frame().with_columns(pl.lit(True).alias("value")), "Boolean"),
        (keyed_frame().drop("value"), "require exactly"),
    ],
)
def test_keyed_rejects(frame, fragment):
    with pytest.raises(InputError, match=None) as info:
        read("avk_ul_keyed_v1", frame, spec(("x", "y")))
    assert fragment in str(info.value)


def test_keyed_missing_declared_field_names_it():
    with pytest.raises(InputError, match=r"require exactly fields \('x', 'y', 'w'\)"):
        read("avk_ul_keyed_v1", keyed_frame(), spec(("x", "y", "w")))


def test_keyed_keys_are_exact_strings():
    frame = pl.DataFrame(
        {"key": ["A", "A ", "A", "A "], "field": ["x", "x", "y", "y"], "value": [1.0] * 4}
    )
    table = read("avk_ul_keyed_v1", frame, spec(("x", "y")))
    assert table.axes[0].keys == ("A", "A ")


def year_frame(years=(1, 2, 3), keys=(0, 1)):
    rows = [
        {"year": y, "key": k, "field": f, "value": 10 * y + k + (0.5 if f == "b" else 0.0)}
        for y in years
        for k in keys
        for f in ("a", "b")
    ]
    return pl.DataFrame(rows)


def test_year_key_selects_one_field():
    table = read("avk_ul_year_key_v1", year_frame(), spec(("b",)))
    assert table.axes[0].name == "policy_year" and table.axes[0].start == 1
    assert table.axes[0].size == 3
    assert table.axes[1].keys == (0, 1)
    np.testing.assert_array_equal(table.values, [[10.5, 11.5], [20.5, 21.5], [30.5, 31.5]])


@pytest.mark.parametrize(
    ("frame", "columns", "fragment"),
    [
        (year_frame(years=(1, 3)), ("a",), "year must be consecutive integers from 1"),
        (year_frame(years=(2, 3)), ("a",), "year must be consecutive integers from 1"),
        (year_frame(keys=(-1, 0)), ("a",), "key must be a nonnegative integer"),
        (
            year_frame().with_columns(pl.col("key").cast(pl.Float64) + 0.5),
            ("a",),
            "key must be a nonnegative integer",
        ),
        (year_frame().tail(-1), ("a",), "missing year/key combination"),
        (year_frame(), ("a", "b"), "select exactly one field"),
        (year_frame(), ("c",), "missing year/key combination"),
        (pl.concat([year_frame(), year_frame().head(1)]), ("a",), "duplicate keys"),
    ],
)
def test_year_key_rejects(frame, columns, fragment):
    with pytest.raises(InputError) as info:
        read("avk_ul_year_key_v1", frame, spec(columns))
    assert fragment in str(info.value)


def test_builtin_formats_cover_unit_linked_tables():
    expected = {
        "ul_funds": "avk_ul_keyed_v1",
        "ul_variants": "avk_ul_keyed_v1",
        "ul_regulatory_caps": "avk_ul_keyed_v1",
        "ul_charge_scales": "avk_ul_year_key_v1",
        "ul_disc_charge_caps": "avk_ul_year_key_v1",
        "ul_riy_caps": "avk_ul_year_key_v1",
        "mortality_charges_ul": "avk_mortality_v1",
        "lapse_rates_ul": "avk_lapse_v1",
        "partial_withdrawals_ul": "avk_lapse_v1",
        "commissions_ul": "avk_commission_v1",
        "ul_asset_returns": "avk_curves_v1",
    }
    assert {name: BUILTIN_FORMATS[name] for name in expected} == expected
