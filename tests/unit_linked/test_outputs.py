"""The UNIT_LINKED output schema and the files a valuation writes."""

import json

import numpy as np
import polars as pl
import pytest

from avk.demo.generate import generate
from avk.products.registry import ProductRegistry
from avk.products.unit_linked.formulas import UnitLinked
from avk.runs.compile import product_kernel


@pytest.fixture(scope="module")
def schema():
    return ProductRegistry.default().for_code("UNIT_LINKED").output_schema("Valuation")


def test_schema_builds_without_duplicates(schema):
    names = [name for name, _, _ in (*schema.keys, *schema.entries)]
    assert len(names) == len(set(names))
    layers = {name.rsplit("_", 1)[-1] for name, _, _ in schema.entries}
    assert layers == {"reserving", "BE", "MC"}
    assert all(name.startswith(("decrements_", "cashflows_", "MCEV_")) for name in names[4:])
    assert not any(name.startswith("cashflows_") and name.endswith("_MC") for name in names)
    assert not any(
        name.startswith("cashflows_") and "profit" in name and name.endswith("_reserving")
        for name in names
    )


def test_every_source_column_is_compiled_for_its_basis(schema):
    keys = set(product_kernel(UnitLinked).layout.keys)
    sources = (
        *schema.entries,
        *schema.keys[1:2],
        *((column, basis) for _, column, basis, _ in schema.seriatim),
    )
    for entry in sources:
        column, basis = entry[-2], entry[-1]
        assert (column, basis) in keys or (column, None) in keys, (column, basis)


@pytest.fixture(scope="module")
def run_three(tmp_path_factory):
    from avk.api import run

    path = generate(tmp_path_factory.mktemp("ul-out"), "UNIT_LINKED", 3, 209)
    config = json.loads(path.read_text())
    config["Output_seriatim_cf_flag"] = 1
    path.write_text(json.dumps(config))
    run(path)
    return path.parent / "output" / "valuation"


def test_seriatim_has_one_row_per_policy_with_step_zero_values(run_three, schema):
    seriatim = pl.read_csv(run_three / "UNIT_LINKED_Base_seriatim_output.csv")
    assert seriatim.height == 3
    assert seriatim["Policy_Number"].n_unique() == 3
    detail = pl.read_csv(run_three / "UNIT_LINKED_Base_output.csv")
    step0 = detail.filter(pl.col("Projection_Step") == 0).sort("Policy_Number")
    seriatim = seriatim.sort("Policy_Number")
    for name in (
        "cashflows_unit_reserve_reserving",
        "cashflows_gf_reserve_held_reserving",
        "cashflows_total_reserve_reserving",
        "MCEV_bel_MC",
        "MCEV_pvfp_MC",
        "MCEV_vif_MC",
        "cashflows_sum_at_risk_BE",
    ):
        np.testing.assert_allclose(seriatim[name], step0[name], rtol=1e-12)
    assert (seriatim["Annualised_premium"] > 0).all()


def test_detailed_output_writes_every_policy_month(run_three, schema):
    detail = pl.read_csv(run_three / "UNIT_LINKED_Base_output.csv")
    aggregate = pl.read_csv(run_three / "UNIT_LINKED_Base_aggregate_output.csv")
    assert detail["Policy_Number"].n_unique() == 3
    assert detail.height == 3 * aggregate.height
    assert detail.columns == [name for name, _, _ in (*schema.keys, *schema.entries)]
    summed = (
        detail.group_by("Projection_Step")
        .agg(pl.col("cashflows_total_reserve_reserving").sum())
        .sort("Projection_Step")
    )
    np.testing.assert_allclose(
        summed["cashflows_total_reserve_reserving"],
        aggregate.sort("Projection_Step")["cashflows_total_reserve_reserving"],
        rtol=1e-10,
    )
    ratio = aggregate["cashflows_total_reserve_pp_reserving"][0]
    lives = aggregate["decrements_lives_total_end_reserving"][0]
    total = aggregate["cashflows_total_reserve_reserving"][0]
    assert ratio == pytest.approx(total / lives, rel=1e-12)
