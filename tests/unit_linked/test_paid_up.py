"""Reduced paid-up transitions, opening holdings, charges and revival expiry."""

import pytest


def test_cessation_enters_paid_up_with_its_slots_and_cover(ul_projection):
    model, frame = ul_projection(1, Duration_in_Months=60, V_rpu_mode=1)
    be = model["be"]
    transferred = be("to_rpu")[1]
    assert be("R_end")[1] == transferred > 0
    assert be("rpu_tpp_close")[1] == pytest.approx(transferred * be("tpp_pp")[1])
    row = frame.row(0, named=True)
    pusa = row["Sum_Assured"] * be("instalments_pp")[1] / row["Instalments_Payable"]
    assert be("pusa_close")[1] == pytest.approx(transferred * pusa)
    for k in (1, 2):
        assert be(f"rpu_{k}_close")[1] == be(f"fund_{k}_close")[1] * transferred
        assert be(f"rpu_{k}_open")[2] == be(f"rpu_{k}_close")[1]
        assert be(f"rpu_{k}_grown")[2] == pytest.approx(
            be(f"rpu_{k}_after_charges")[2] * (1 + be(f"fund_{k}_growth_rate")[2])
        )
        assert be(f"rpu_{k}_after_fmc")[2] == pytest.approx(
            be(f"rpu_{k}_grown")[2] * (1 - be(f"fund_{k}_fmc_rate")[2])
        )
    assert be("fund_1_growth_rate")[2] != be("fund_2_growth_rate")[2]


@pytest.mark.parametrize("death_type", [1, 2])
def test_paid_up_status_opens_only_paid_up_holding_and_charges_its_risk(ul_projection, death_type):
    model, frame = ul_projection(4, V_death_benefit_type=death_type)
    row = frame.row(0, named=True)
    for basis in ("reserving", "be", "mc"):
        data = model[basis]
        assert data("pusa_close")[0] == row["Paid_Up_Sum_Assured"]
        assert data("rpu_tpp_close")[0] == row["Premiums_Paid_To_Date"]
        assert data("fund_close_total")[0] == 0
        assert data("R_end")[0] == 1
        for k in (1, 2):
            assert data(f"rpu_{k}_close")[0] == row[f"Fund_{k}_Value"]
            assert data(f"rpu_{k}_fmc")[0] == 0
        assert not data("premium_pp").any()
        assert not data("additions_pp").any()
        insured = row["Paid_Up_Sum_Assured"]
        floor = row["V_min_db_premium_multiple"] * row["Premiums_Paid_To_Date"]
        fund = data("rpu_open_total")[1] - data("rpu_admin_req")[1] - data("rpu_gc_req")[1]
        expected = (
            max(max(insured, floor) - fund, 0) if death_type == 1 else max(insured, floor - fund)
        )
        assert data("rpu_sar")[1] == pytest.approx(expected)
        assert data("rpu_mc")[1] == pytest.approx(expected * data("mc_rate")[1] / 12000)


def test_revival_expiry_is_a_monthly_rate_on_remaining_lives(ul_projection):
    model, _ = ul_projection(4, V_rpu_mode=2, V_revival_period_months=36)
    be = model["be"]
    after_surrenders = 1 - be("deaths_R")[1] - be("surrenders_R")[1]
    assert be("expiries_R")[1] == pytest.approx(after_surrenders / 36)
    assert be("R_end")[1] == pytest.approx(after_surrenders * (1 - 1 / 36))
    assert be("rpu_close_total")[1] == pytest.approx(be("rpu_after_fmc_total")[1] * be("R_end")[1])


def test_mode_zero_pays_cessation_outside_lock_in(ul_projection):
    model, _ = ul_projection(0, Duration_in_Months=60, V_rpu_mode=0)
    be = model["be"]
    assert be("cessations_A")[1] > 0
    assert be("paid_out_A")[1] == pytest.approx(be("surrenders_A")[1] + be("cessations_A")[1])
    assert not be("rpu_close_total").any()
