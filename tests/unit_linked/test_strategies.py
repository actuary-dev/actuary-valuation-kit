"""One-policy lifecycle and systematic fund transfer checks."""

import numpy as np
import polars as pl
import pytest

from avk.products.unit_linked.validation import UnitLinkedPolicyValidator


@pytest.mark.parametrize(("mode", "age"), [(1, 0), (2, 40)])
def test_lifecycle_uses_the_age_or_remaining_year_schedule(ul_projection, mode, age):
    # Two schedule rows: ascending age gives 70% then 40%; remaining years reverses.
    schedule = np.array([[0.7], [0.4]]) if mode == 1 else np.array([[0.4], [0.7]])
    model, _ = ul_projection(
        1,
        Duration_in_Months=10,
        Age_at_Entry=age,
        Policy_Term=2,
        Fund_1_Value=800,
        Fund_2_Value=200,
        Fund_1_FMC=0,
        Fund_2_FMC=0,
        Fund_1_Alpha=0,
        Fund_2_Alpha=0,
        Instalment_Premium=0,
        V_pw_allowed=0,
        V_mortality_charge_multiplier=0,
        V_loyalty_on=0,
        Strategy_Mode=mode,
        Strategy_Source_Slot=1,
        Strategy_Target_2=1,
        table_overrides={
            "ul_strategies/share": schedule,
            "ul_charge_scales/admin_charge_monthly": 0,
        },
    )
    # MC certainty equivalent grows both slots at one rate.
    mc = model["mc"]
    assert mc("fund_1_open")[:3] == pytest.approx([800, 700, mc("fund_close_total")[1] * 0.7])
    assert mc("fund_2_open")[1] == pytest.approx(300)
    assert mc("switch_out_total")[:3] == pytest.approx([0, 100, 0])
    assert mc("fund_1_open")[3] == pytest.approx(mc("fund_close_total")[2] * 0.4)
    assert mc("fund_2_open")[3] == pytest.approx(mc("fund_close_total")[2] * 0.6)


@pytest.mark.parametrize(("mode", "sold"), [(3, 150), (4, 200), (4, 600)])
def test_stp_splits_net_switch_and_preserves_the_topup_tag(ul_projection, mode, sold):
    model, _ = ul_projection(
        2,
        Duration_in_Months=72,
        Fund_1_Value=600,
        Fund_1_Topup_Value=60,
        Fund_2_Value=200,
        Fund_3_Value=100,
        Fund_4_Value=0,
        Fund_5_Value=0,
        V_auto_rebalance=1,
        V_topup_on=1,
        V_switch_charge=10,
        Instalment_Premium=0,
        Strategy_Mode=mode,
        Strategy_Source_Slot=1,
        Strategy_Target_2=0.25,
        Strategy_Target_3=0.75,
        Strategy_Amount=700 if sold == 600 else 200,
        table_overrides={"ul_strategies/share": 0.25},
    )
    be = model["be"]
    assert be("switch_out_total")[0] == 0
    assert be("fund_1_open")[1] == pytest.approx(600 - sold)
    assert be("fund_2_open")[1] == pytest.approx(200 + (sold - 10) * 0.25)
    assert be("fund_3_open")[1] == pytest.approx(100 + (sold - 10) * 0.75)
    assert be("fund_1_topup_open")[1] == pytest.approx((600 - sold) * 0.1)
    assert be("fund_2_topup_open")[1] == pytest.approx((sold - 10) * 0.025)
    assert be("fund_3_topup_open")[1] == pytest.approx((sold - 10) * 0.075)
    assert be("fund_open_total")[1] == pytest.approx(890)
    assert be("switch_charge_income")[1] == pytest.approx(10 * be("A_begin")[1])
    assert be("premium_income")[1] == 0


@pytest.mark.parametrize("strategy", [-1, 1.5, None])
def test_strategy_id_is_explicitly_validated(book, strategy):
    policies, _ = book
    policies = policies.with_columns(pl.lit(strategy).alias("Fund Strategy"))
    messages = [issue.message for issue in UnitLinkedPolicyValidator().validate(policies)]
    assert any("Fund Strategy" in message for message in messages)
