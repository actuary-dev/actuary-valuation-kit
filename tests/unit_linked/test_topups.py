"""Hand calculations for top-up premiums, cover and locked units."""

import polars as pl
import pytest
from conftest import holding, policy

from avk.api import run
from avk.demo.generate import generate
from avk.products.unit_linked.validation import UnitLinkedPolicyValidator
from avk.runs.check import check
from avk.runtime.errors import InputError


def test_topups_use_separate_allocation_scale_and_add_death_cover(ul_projection):
    model, _ = ul_projection(
        1,
        Duration_in_Months=70,
        Instalment_Premium=0,
        Single_Top_Up_Premium=300,
        Single_Top_Up_Policy_Month=72,
        Regular_Top_Up_Premium=200,
        V_topup_on=1,
        V_topup_sa_multiple=1.25,
        V_pw_allowed=0,
        Sum_Assured=1000,
        V_min_db_premium_multiple=0,
        table_overrides={"ul_charge_scales/topup_allocation_rate": 0.1},
    )
    be = model["be"]
    assert be("topup_pp")[:3] == pytest.approx([0, 200, 500])
    for step, (gross, charge, cover) in enumerate(((200, 20, 250), (500, 50, 875)), 1):
        assert be("premium_income")[step] == pytest.approx(gross * be("A_begin")[step])
        assert be("pac_income")[step] == pytest.approx(charge * be("A_begin")[step])
        assert be("tpp_pp")[step] == 600000 + (200 if step == 1 else 700)
        assert be("sa_eff")[step] == 1000 + cover
        assert be("death_non_unit_A")[step] == pytest.approx((1000 + cover) * be("deaths_A")[step])
        for slot, share in ((1, 0.4), (2, 0.6)):
            assert be(f"fund_{slot}_after_premium")[step] - be(f"fund_{slot}_open")[step] == (
                pytest.approx((gross - charge) * share)
            )


def test_partial_withdrawals_leave_locked_topup_units_invested(ul_projection):
    model, frame = ul_projection(
        5,
        Duration_in_Months=73,
        Fund_1_Value=280,
        Fund_1_Topup_Value=180,
        Fund_1_FMC=0,
        Fund_1_Alpha=0,
        Top_Up_Premiums_Paid_To_Date=200,
        Last_Top_Up_Policy_Month=73,
        V_topup_on=1,
        V_topup_lock_in_months=2,
        V_pw_allowed=1,
        V_pw_start_year=1,
        V_mortality_charge_multiplier=0,
        table_overrides={
            "partial_withdrawals_ul": 1,
            "ul_charge_scales/admin_charge_monthly": 0,
        },
    )
    be = model["be"]
    assert frame["Fund_1_Value"].item() == 280
    assert be("topup_lock_active")[:3] == pytest.approx([1, 1, 0])
    assert be("fund_1_topup_close")[0] == 180
    assert be("fund_1_topup_units")[0] == pytest.approx(180 / frame["Fund_1_Unit_Price"].item())
    assert be("pw_pp")[1] == 100
    close = 180 * (1 + be("fund_1_growth_rate")[1])
    assert be("fund_1_topup_close")[1] == pytest.approx(close)
    assert be("pw_pp")[2] == pytest.approx(close)
    assert be("fund_1_topup_close")[2] == 0


@pytest.mark.parametrize("value", [-1.0, float("nan"), None])
def test_topup_amounts_are_validated_when_supplied(book, value):
    policies, _ = book
    policies = policies.with_columns(pl.lit(value).alias("Single Top-Up Premium"))
    messages = [issue.message for issue in UnitLinkedPolicyValidator().validate(policies)]
    assert any("Single Top-Up Premium" in message for message in messages)


def test_paid_up_conversion_carries_full_topup_cover(ul_projection):
    model, frame = ul_projection(
        0,
        Duration_in_Months=72,
        V_topup_on=1,
        V_topup_sa_multiple=1.25,
        Top_Up_Premiums_Paid_To_Date=200,
        Last_Top_Up_Policy_Month=72,
        V_rpu_mode=1,
        V_lock_in_months=0,
    )
    be = model["be"]
    assert be("to_rpu")[1] > 0
    base_paid_up = (
        frame["Sum_Assured"].item() * be("instalments_pp")[1] / frame["Instalments_Payable"].item()
    )
    assert be("pusa_close")[1] == pytest.approx(be("to_rpu")[1] * (base_paid_up + 250))


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("missing", "topup_on requires policy columns"),
        ("month", "future Single Top-Up Policy Month"),
        ("allocation", "allocations of a policy with future top-ups"),
        ("cap", "topup_allocation_rate above pac_max"),
        ("strategy", "strategy source and targets must be held selectable funds"),
        ("switch_cap", "switch_charge above switch_charge_max"),
        ("weights", "target weights must sum to 1 and exclude the source slot"),
        (None, None),
    ],
)
def test_preflight_and_valuation_for_topups_and_a_strategy(tmp_path, defect, message):
    config = generate(tmp_path, "UNIT_LINKED", 1, 209)
    fields = {
        "Annualised Premium": 1200,
        "Premium Frequency": 12,
        "Single Top-Up Premium": 300,
        "Single Top-Up Policy Month": 70 if defect == "month" else 72,
        "Regular Top-Up Premium": 200,
        "Top-Up Premiums Paid To Date": 0,
        "Last Top-Up Policy Month": 0,
        "Fund Strategy": 1,
    }
    if defect == "missing":
        del fields["Last Top-Up Policy Month"]
    if defect == "allocation":
        fields["Premium Payment Term (Years)"] = 5
        fields["Regular Top-Up Premium"] = 0
    pl.DataFrame([policy("UL1", "ULIP_CLASSIC", **fields)]).write_csv(tmp_path / "policies.csv")
    pl.DataFrame(
        [
            holding(
                "UL1",
                "DT_GILT",
                10,
                0.3 if defect == "allocation" else 0.4,
                **{"Top-Up Units": 0},
            ),
            holding("UL1", "EQ_INDEX", 10, 0.6, **{"Top-Up Units": 0}),
        ]
    ).write_csv(tmp_path / "policy_funds.csv")
    basis = tmp_path / "basis"
    variants = basis / "ul_variants.csv"
    pl.read_csv(variants).with_columns(
        pl.when(pl.col("key") == "ULIP_CLASSIC")
        .then(
            pl.col("field").replace_strict(
                {
                    "topup_on": 1.0,
                    "topup_sa_multiple": 1.25,
                    "switch_charge": 501.0 if defect == "switch_cap" else 10.0,
                },
                default=pl.col("value"),
            )
        )
        .otherwise(pl.col("value"))
        .alias("value")
    ).write_csv(variants)
    scales = basis / "ul_charge_scales.csv"
    pl.read_csv(scales).with_columns(
        pl.when((pl.col("field") == "topup_allocation_rate") & (pl.col("key") == 0))
        .then(0.2 if defect == "cap" else 0.1)
        .otherwise(pl.col("value"))
        .alias("value")
    ).write_csv(scales)
    strategies = basis / "ul_strategies.csv"
    off = pl.read_csv(strategies)
    on = off.with_columns(
        pl.lit(1, dtype=pl.Int64).alias("key"),
        pl.col("field")
        .replace_strict(
            {
                "mode": 3.0,
                "source_slot": 3.0 if defect == "strategy" else 2.0,
                "share": 0.25,
                "target_1": 0.5 if defect == "weights" else 1.0,
            },
            default=0.0,
        )
        .alias("value"),
    )
    pl.concat([off, on]).write_csv(strategies)
    if message:
        with pytest.raises(InputError, match=message):
            check(config)
        return
    report = check(config)
    assert report.points.frame["Fund_1_Selectable"].item() == 1
    assert report.points.frame["Strategy_Mode"].item() == 3
    assert report.points.frame["Strategy_Source_Slot"].item() == 2
    run(config)
    aggregate = pl.read_csv(tmp_path / "output/valuation/UNIT_LINKED_Base_aggregate_output.csv")
    assert aggregate["cashflows_premiums_BE"][1] == 300
    assert aggregate["cashflows_premiums_allocated_BE"][1] == 278
    assert aggregate["cashflows_charges_allocation_BE"][1] == 22
