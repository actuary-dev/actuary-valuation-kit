"""Path-specific fund prices and maturity payments above the units."""

from dataclasses import replace

import numpy as np
import polars as pl
import pytest
from conftest import holding, policy

from avk.api import run
from avk.demo.generate import generate
from avk.products.unit_linked.bindings import ASSET_CLASSES


@pytest.mark.parametrize(("start", "seed", "expected"), [(1, 12, 60), (120, 0, 0)])
def test_highest_nav_peaks_are_per_path_and_inside_the_window(
    ul_projection, projection_inputs, start, seed, expected
):
    report, _ = projection_inputs
    variables = {
        name: np.zeros((2, values.shape[1])) for name, values in report.scenarios.variables.items()
    }
    variables["ret_eq_large"][:, 1:3] = [[0.5, -0.4], [0.1, 13 / 11 - 1]]
    scenarios = replace(
        report.scenarios, variables=variables, ids=("spike", "steady"), weights=np.full(2, 0.5)
    )
    model, _ = ul_projection(
        5,
        scenarios=scenarios,
        Duration_in_Months=118,
        Policy_Term=10,
        Fund_1_Value=100,
        Fund_1_Unit_Price=10,
        Fund_1_Guarantee_Type=1,
        Fund_1_Guaranteed_Price=seed,
        Fund_1_FMC=0,
        Fund_1_Alpha=0,
        V_highest_nav_start_month=start,
        V_mortality_charge_multiplier=0,
        V_pw_allowed=0,
        table_overrides={
            "mortality": 0,
            "lapse_rates_ul": 0,
            "ul_charge_scales/admin_charge_monthly": 0,
        },
        **{f"Fund_1_W_{asset}": int(asset == "eq_large") for asset in ASSET_CLASSES},
    )
    be = model["be"]
    np.testing.assert_allclose(be("fund_1_nav")[:, :3], [[10, 15, 9], [10, 11, 13]])
    np.testing.assert_allclose(be("fund_1_highest_nav")[:, 0], [seed, seed])
    np.testing.assert_allclose(be("maturity_unit_A")[:, 2], [90, 130])
    np.testing.assert_allclose(be("highest_nav_cost")[:, 2], [expected, 0])
    np.testing.assert_allclose(be("non_unit_benefit_outgo")[:, 2], [expected, 0])
    np.testing.assert_array_equal(be("highest_nav_cost")[:, :2], 0)


@pytest.mark.parametrize(("row", "state"), [(5, "A"), (4, "R")])
@pytest.mark.parametrize(("guarantee_type", "expected"), [(1, 10), (2, 0)])
def test_highest_nav_at_valuation_month_settlement(
    ul_projection, row, state, guarantee_type, expected
):
    model, _ = ul_projection(
        row,
        Duration_in_Months=120,
        Policy_Term=10,
        Fund_1_Value=50,
        Fund_2_Value=0,
        Fund_1_Unit_Price=10,
        Fund_1_Guarantee_Type=guarantee_type,
        Fund_1_Guaranteed_Price=12,
        V_highest_nav_start_month=1,
    )
    for basis in ("reserving", "be", "mc"):
        data = model[basis]
        assert data(f"maturity_unit_{state}")[1] == 50
        assert data("highest_nav_cost")[:2] == pytest.approx([0, expected])
        assert data("non_unit_benefit_outgo")[1] == expected


def test_paid_up_nav_is_net_of_fmc_and_weighted_by_maturity_lives(ul_projection):
    model, _ = ul_projection(
        4,
        Duration_in_Months=119,
        Policy_Term=10,
        Fund_1_Value=50,
        Fund_2_Value=0,
        Fund_1_Unit_Price=10,
        Fund_1_Guarantee_Type=1,
        Fund_1_Guaranteed_Price=12,
        Fund_1_FMC=1 - 0.9**12,
        Fund_1_Alpha=0,
        V_rpu_mode=1,
        V_highest_nav_start_month=1,
        V_mortality_charge_multiplier=0,
        table_overrides={"ul_charge_scales/admin_charge_monthly": 0},
        **{f"Fund_1_W_{asset}": 0 for asset in ASSET_CLASSES},
    )
    be = model["be"]
    survivors = 1 - be("q")[1]
    assert 0 < survivors < 1
    assert be("fund_1_nav")[:2] == pytest.approx([10, 9])
    assert be("maturity_unit_R")[1] == pytest.approx(45 * survivors)
    assert be("highest_nav_cost")[1] == pytest.approx(15 * survivors)


def test_highest_nav_shortfall_is_reported_through_valuation(tmp_path):
    config = generate(tmp_path, "UNIT_LINKED", 1, 209)
    pl.DataFrame(
        [
            policy(
                "UL1",
                "ULIP_CLASSIC",
                **{
                    "Policy Start Date": "2025-01-01",
                    "Status Date": "2025-01-01",
                    "Policy Term (Years)": 1,
                    "Premium Payment Term (Years)": 1,
                    "Age at Policy Start": 39,
                },
            )
        ]
    ).write_csv(tmp_path / "policies.csv")
    basis = tmp_path / "basis"
    funds = pl.read_csv(basis / "ul_funds.csv")
    price = funds.filter((pl.col("key") == "GT_HIGHEST_NAV") & (pl.col("field") == "unit_price"))[
        "value"
    ].item()
    pl.DataFrame(
        [holding("UL1", "GT_HIGHEST_NAV", 5, 1, **{"Guaranteed Unit Price": 2 * price})]
    ).write_csv(tmp_path / "policy_funds.csv")
    variants_path = basis / "ul_variants.csv"
    pl.read_csv(variants_path).with_columns(
        pl.when((pl.col("key") == "ULIP_CLASSIC") & (pl.col("field") == "highest_nav_start_month"))
        .then(1)
        .otherwise(pl.col("value"))
        .alias("value")
    ).write_csv(variants_path)
    run(config)
    aggregate = pl.read_csv(tmp_path / "output/valuation/UNIT_LINKED_Base_aggregate_output.csv")
    for suffix in ("reserving", "BE", "MC"):
        assert aggregate[f"benefits_non_unit_highest_nav_{suffix}"][:2].to_list() == pytest.approx(
            [0, 5 * price]
        )
