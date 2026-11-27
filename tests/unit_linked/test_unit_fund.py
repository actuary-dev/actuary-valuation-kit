"""Scalar checks of active-fund timing, fund-specific growth and risk charges."""

import numpy as np
import pytest

from avk.products.unit_linked.bindings import ASSET_CLASSES


def monthly_return(annual):
    return (1 + annual) ** (1 / 12) - 1


def monthly_charge(annual):
    return 1 - (1 - annual) ** (1 / 12)


def test_one_fund_monthly_roll_for_two_years(ul_projection):
    model, frame = ul_projection(
        0,
        Duration_in_Months=12,
        V_pw_start_year=2,
        V_guarantee_charge=0.003,
        EMR=1.25,
        Flat_Extra=0.8,
        Flat_Extra_Term_Months=15,
    )
    row = frame.row(0, named=True)
    be = model["be"]
    fund, tpp = row["Fund_1_Value"], row["Premiums_Paid_To_Date"]
    assert be("fund_close_total")[0] == fund

    def scale(name, year):
        return model.table(f"ul_charge_scales/{name}", year, row["Variant_Id"])

    for step in range(1, 25):
        pm = 12 + step
        year = (pm - 1) // 12 + 1
        age = row["Age_at_Entry"] + year - 1
        premium = row["Instalment_Premium"] if pm % 12 == 1 else 0
        tpp += premium
        pac = premium * scale("premium_allocation_rate", year)
        after_premium = fund + premium - pac
        pw = after_premium * monthly_charge(
            model.table("partial_withdrawals_ul", year, row["Distribution_Channel"])
        )
        admin = scale("admin_charge_monthly", year) * (1 + row["V_admin_escalation"]) ** (year - 1)
        gc = after_premium * monthly_charge(row["V_guarantee_charge"])
        sar = max(
            max(row["Sum_Assured"], row["V_min_db_premium_multiple"] * tpp)
            - (after_premium - pw - admin - gc),
            0,
        )
        rate = model.table("mortality_charges_ul", age, row["Charge_Column"])
        rate *= row["EMR"] * row["V_mortality_charge_multiplier"]
        rate += row["Flat_Extra"] * (pm <= row["Flat_Extra_Term_Months"])
        mc = sar * rate / 12000
        after_charges = after_premium - pw - admin - gc - mc
        growth = sum(
            row[f"Fund_1_W_{asset}"] * model.scenario(f"ret_{asset}")[step]
            for asset in ASSET_CLASSES
        ) + monthly_return(row["Fund_1_Alpha"])
        growing = after_charges * (1 + growth)
        fmc = growing * monthly_charge(row["Fund_1_FMC"])
        fund = growing - fmc
        for column, expected in {
            "premium_pp": premium,
            "tpp_pp": tpp,
            "pac_pp": pac,
            "fund_after_premium_total": after_premium,
            "pw_pp": pw,
            "admin_pp": admin,
            "gc_pp": gc,
            "sar": sar,
            "mc_pp": mc,
            "fund_after_charges_total": after_charges,
            "fund_1_fmc": fmc,
            "fund_close_total": fund,
        }.items():
            assert be(column)[step] == pytest.approx(expected, rel=1e-9), (step, column)


def test_fund_mix_rebalances_then_drifts_and_empty_slots_stay_zero(ul_projection):
    model, frame = ul_projection(
        1,
        Duration_in_Months=11,
        V_auto_rebalance=1,
        V_pw_allowed=0,
        V_loyalty_on=0,
        V_guaranteed_addition_rate=0,
    )
    be = model["be"]
    share = frame["Fund_1_Allocation"].item()
    assert be("fund_1_open")[1] != pytest.approx(be("fund_open_total")[1] * share)
    for step in (2, 14, 26):
        assert be("fund_1_open")[step] == pytest.approx(be("fund_open_total")[step] * share)
        assert be("fund_1_growth_rate")[step] != be("fund_2_growth_rate")[step]
        assert be("fund_1_close")[step] / be("fund_close_total")[step] != pytest.approx(share)
        for slot in (1, 2):
            before = be(f"fund_{slot}_after_premium")[step]
            after = be(f"fund_{slot}_after_charges")[step]
            assert (before - after) / before == pytest.approx(
                be("deduction_total")[step] / be("fund_after_premium_total")[step], rel=1e-9
            )
            assert be(f"fund_{slot}_fmc")[step] == pytest.approx(
                be(f"fund_{slot}_grown")[step] * monthly_charge(frame[f"Fund_{slot}_FMC"].item())
            )
    for slot in (3, 4, 5):
        for stage in ("open", "after_premium", "after_charges", "grown", "fmc", "close"):
            assert not np.any(be(f"fund_{slot}_{stage}"))


@pytest.mark.parametrize("death_type", [1, 2])
def test_sum_at_risk_with_fund_above_both_floors(ul_projection, death_type):
    model, _ = ul_projection(0, Fund_1_Value=3e6, Sum_Assured=1e6, V_death_benefit_type=death_type)
    be = model["be"]
    assert be("sar")[1] == (0 if death_type == 1 else be("sa_eff")[1])
    assert (be("mc_pp")[1] == 0) == (death_type == 1)


def test_withdrawal_cover_reduction_uses_latest_two_policy_years(ul_projection):
    model, _ = ul_projection(
        0,
        Duration_in_Months=70,
        V_pw_reduces_sa=1,
        V_pw_allowed=1,
        PW_Current_Year=10000.0,
        PW_Previous_Year=20000.0,
        Sum_Assured=1000000.0,
    )
    be = model["be"]
    assert be("sa_eff")[1] == 970000
    assert be("sa_eff")[2] == pytest.approx(970000 - be("pw_pp")[1])
    assert be("pw_last_year_pp")[3] == pytest.approx(10000 + sum(be("pw_pp")[1:3]))
    assert be("sa_eff")[3] == pytest.approx(1000000 - be("pw_last_year_pp")[3])
