"""Independent checks of the monthly rates and routing of expected lives."""

import numpy as np
import pytest

from avk.runs.cases import Case, Shock


def monthly(annual):
    return 1 - (1 - annual) ** (1 / 12)


@pytest.mark.parametrize(
    ("frequency", "due"), [(1, [1]), (2, [1, 7]), (4, [1, 4, 7, 10]), (12, list(range(1, 13)))]
)
def test_decrement_rates_match_modal_math(ul_projection, frequency, due):
    model, frame = ul_projection(
        0, Duration_in_Months=12, Premium_Frequency=frequency, Smoker_Code=1, EMR=1.25
    )
    row = frame.row(0, named=True)
    be, reserving = model["be"], model["reserving"]
    assert np.flatnonzero(be("premium_due")[:13]).tolist() == due
    assert np.flatnonzero(be("w_cessation")[:13]).tolist() == due
    experience = model.table("mortality", row["Age_at_Entry"] + 1, row["Gender_Code"])
    params = model.params("reserving")
    annual = (
        experience * params["experience_mortality_pct"] * params["smoker_mortality_loading"] * 1.25
    )
    assert be("q")[1] == pytest.approx(monthly(annual), rel=1e-12)
    assert reserving("q")[1] == pytest.approx(
        monthly(annual * (1 + params["prudent_margin_mortality"])), rel=1e-12
    )
    share = params["surrender_share"]
    lapse = model.table("lapse_rates_ul", 2, row["Distribution_Channel"])
    assert be("w_surrender")[2] == pytest.approx(monthly(lapse * share), rel=1e-12)
    assert be("w_cessation")[1] == pytest.approx(
        1 - (1 - lapse * (1 - share)) ** (1 / frequency), rel=1e-12
    )
    assert reserving("w_surrender")[2] > be("w_surrender")[2]
    assert reserving("w_cessation")[1] > be("w_cessation")[1]


@pytest.mark.parametrize("single", [True, False])
def test_full_surrender_rate_after_payment_term_or_for_single(ul_projection, single):
    model, row = ul_projection(
        0,
        Duration_in_Months=60,
        V_single_premium=int(single),
        Premium_Frequency=0 if single else 4,
        Premium_Payment_Term=0 if single else 5,
    )
    be = model["be"]
    assert not be("premium_due").any()
    assert not be("w_cessation").any()
    lapse = model.table("lapse_rates_ul", 6, row["Distribution_Channel"].item())
    assert be("w_surrender")[1] == pytest.approx(monthly(lapse), rel=1e-12)


@pytest.mark.parametrize("status", [0, 1, 2])
def test_lives_and_cumulative_exits_reconcile(ul_projection, status):
    model, _ = ul_projection(
        0,
        Duration_in_Months=48,
        Policy_Term=10,
        Premium_Payment_Term=10,
        Policy_Status=status,
        Premium_Frequency=12,
    )
    for basis in ("be", "reserving", "mc"):
        data = model[basis]
        exits = sum(
            data(name)
            for name in (
                "deaths_A",
                "deaths_D",
                "deaths_R",
                "paid_out_A",
                "lockin_exits_D",
                "surrenders_R",
                "expiries_R",
                "maturities",
            )
        )
        np.testing.assert_allclose(data("lives_end") + np.cumsum(exits), 1, rtol=1e-9, atol=1e-10)
        assert [data(name)[0] for name in ("A_end", "D_end", "R_end")] == [
            float(status == i) for i in range(3)
        ]
        assert data("lives_end")[72] == 0
        assert exits[0] == 0


@pytest.mark.parametrize(
    ("month", "dpf", "mode", "route"),
    [
        (49, 1, 2, "to_dpf"),
        (49, 0, 2, "paid_out_A"),
        (61, 1, 2, "to_rpu"),
        (61, 1, 1, "to_rpu"),
        (61, 1, 0, "paid_out_A"),
    ],
)
def test_discontinuance_routing(ul_projection, month, dpf, mode, route):
    model, _ = ul_projection(0, Duration_in_Months=month - 1, V_dpf_enabled=dpf, V_rpu_mode=mode)
    be = model["be"]
    assert be("surrenders_A")[1] > 0
    assert be("cessations_A")[1] > 0
    expected = {
        "to_dpf": be("surrenders_A")[1] + be("cessations_A")[1],
        "to_rpu": be("cessations_A")[1],
        "paid_out_A": be("surrenders_A")[1] + be("cessations_A")[1],
    }
    assert be(route)[1] == pytest.approx(expected[route], rel=1e-12)


def test_case_shocks_follow_the_term_conventions(ul_projection):
    case = Case(
        "shock",
        {
            "mortality": Shock(0.02, 1.5, 1, 1),
            "lapse": Shock(-0.10, 1, 1, 1, maximum_decrease=0.02),
        },
        mass_lapse=0.3,
    )
    model, row = ul_projection(0, case=case)
    base, _ = ul_projection(0)
    be = model["be"]
    annual = base["be"]("mortality_rate")[1]
    assert be("q")[1] == pytest.approx(monthly((annual + 0.02) * 1.5), rel=1e-12)
    year = int(be("policy_year")[1])
    lapse = model.table("lapse_rates_ul", year, row["Distribution_Channel"].item())
    assert be("discontinuance_rate")[1] == pytest.approx(lapse - 0.02, rel=1e-12)
    surrender = be("w_surrender")[1]
    assert be("surrenders_A")[1] == pytest.approx(
        (1 - be("q")[1]) * (surrender + (1 - surrender) * 0.3), rel=1e-12
    )
    assert be("q")[2] == base["be"]("q")[2]
