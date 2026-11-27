"""Single-life projection, net yield and reduction in yield (RIY), checked by hand."""

import numpy as np
import pytest

from avk.products.unit_linked.bindings import ASSET_CLASSES
from avk.products.unit_linked.illustration import (
    FEATURES,
    Case,
    ChargeSchedule,
    Gross,
    net_yield,
    project,
    riy,
    year_end,
)
from avk.runs.ul_compliance import case_from_row

NO_FEATURES = {
    "single_premium": 0,
    "death_benefit_type": 1,
    "min_db_premium_multiple": 0.0,
    "lock_in_months": 60,
    "dpf_enabled": 1,
    "loyalty_on": 0,
    "loyalty_basis": 1,
    "loyalty_start_year": 10,
    "loyalty_requires_full_premiums": 0,
    "guaranteed_addition_rate": 0.0,
    "romc_fraction": 0.0,
    "ropac_fraction": 0.0,
    "roadmin_fraction": 0.0,
    "gmmb_on": 0,
    "gmmb_premium_multiple": 0.0,
    "guarantee_charge": 0.0,
    "admin_escalation": 0.0,
    "mortality_charge_multiplier": 1.0,
    "disc_ap_threshold": 50000.0,
    "auto_rebalance": 0,
    "riy_additions_on": 1,
}
assert set(NO_FEATURES) == set(FEATURES)


def schedule(pac=0.05, admin=0.0, cap=0.04, mortality=2.0):
    return ChargeSchedule(
        pac_rate=(pac,),
        admin=(admin,),
        loyalty_rate=(0.0,),
        booster_rate=(0.0,),
        disc_pct_low=(0.1,),
        disc_cap_low=(3000.0,),
        disc_pct_high=(0.05,),
        disc_cap_high=(6000.0,),
        riy_cap=(cap,),
        mortality_per_mille=(mortality,),
    )


def plain_case(**changes):
    values = {
        "term_years": 10,
        "payment_years": 0,
        "frequency": 0,
        "instalment": 100_000.0,
        "annualised_premium": 100_000.0,
        "instalments_payable": 1,
        "sum_assured": 125_000.0,
        "entry_age": 35,
        "emr": 1.0,
        "flat_extra": 0.0,
        "flat_extra_months": 0,
        "features": {**NO_FEATURES, "single_premium": 1},
        "allocations": (1.0,),
        "fmcs": (0.0135,),
        "schedule": schedule(),
    }
    values.update(changes)
    return Case(**values)


def test_single_premium_net_yield_matches_the_closed_form():
    """Premium 100,000 less 5% allocation, no other charge but a 1.35% FMC, 8% gross."""
    case = plain_case()
    gross = Gross.of(0.08)
    path = project(case, gross, risk_charges=False)
    measured = riy(path)
    for year, fund, net, value in zip(
        measured.years, path.year_end(path.fund)[4:], measured.net_yield, measured.riy, strict=True
    ):
        # Each month multiplies the fund by (1 + g_m)(1 - f)^(1/12): a year by 1.08 (1 - f).
        expected = 95_000.0 * (1.08 * (1 - 0.0135)) ** year
        assert fund == pytest.approx(expected, rel=1e-12)
        independent = (expected / 100_000.0) ** (1 / year) - 1
        assert net == pytest.approx(independent, abs=1e-12)
        assert value == pytest.approx(0.08 - independent, abs=1e-12)
    assert list(measured.years) == [5, 6, 7, 8, 9, 10]
    assert np.all(measured.cap == 0.04)
    assert np.allclose(measured.excess, measured.riy - 0.04, atol=1e-15)


def test_regular_premium_net_yield_against_polynomial_roots():
    """Five annual instalments of 60,000, 4% allocation charge, 90 a month, two funds, 6%."""
    case = plain_case(
        term_years=8,
        payment_years=5,
        frequency=1,
        instalment=60_000.0,
        annualised_premium=60_000.0,
        instalments_payable=5,
        features=NO_FEATURES,
        allocations=(0.6, 0.4),
        fmcs=(0.01, 0.015),
        schedule=schedule(pac=0.04, admin=90.0),
    )
    gross = Gross.of(0.06)
    path = project(case, gross, risk_charges=False)

    # An independent monthly roll: premium and allocation first, then the flat charge pro rata,
    # then growth and each fund's own management charge.
    funds = [0.0, 0.0]
    for month in range(1, 97):
        if month % 12 == 1 and month <= 60:
            funds = [f + 60_000.0 * 0.96 * w for f, w in zip(funds, (0.6, 0.4), strict=True)]
        total = sum(funds)
        funds = [f * (1 - 90.0 / total) for f in funds]
        funds = [
            f * 1.06 ** (1 / 12) * (1 - c) ** (1 / 12)
            for f, c in zip(funds, (0.01, 0.015), strict=True)
        ]
        if month % 12 == 0:
            assert path.fund[month - 1] == pytest.approx(sum(funds), rel=1e-12), month
            year = month // 12
            if year >= 5:
                # sum P x^(year - j) = F for the five instalments at times 0..4: a polynomial.
                coefficients = np.zeros(year + 1)
                coefficients[:5] = 60_000.0
                coefficients[-1] = -sum(funds)
                roots = np.roots(coefficients)
                real = roots[np.abs(roots.imag) < 1e-9].real
                positive = real[real > 0]
                assert len(positive) == 1
                measured = riy(path)
                index = year - 5
                assert measured.net_yield[index] == pytest.approx(positive[0] - 1, abs=1e-10)
                assert measured.riy[index] == pytest.approx(0.06 - (positive[0] - 1), abs=1e-10)


def test_net_yield_solves_irr_and_handles_a_lost_fund():
    times = np.array([0.0, 1.0, 2.0])
    amounts = np.array([100.0, 100.0, 100.0])
    value = float(np.sum(amounts * 1.07 ** (4.0 - times)))
    assert net_yield(times, amounts, 4.0, value) == pytest.approx(0.07, abs=1e-13)
    assert net_yield(times, amounts, 4.0, 0.0) == -1.0
    # A negative yield: the fund is below the premiums paid.
    assert net_yield(times, amounts, 4.0, 250.0) < 0


def test_risk_charges_are_left_out_of_the_riy_basis():
    base = {"emr": 2.0, "flat_extra": 5.0, "flat_extra_months": 60}
    risky = plain_case(
        **base,
        features={**NO_FEATURES, "single_premium": 1, "guarantee_charge": 0.004},
    )
    clean = plain_case()
    gross = Gross.of(0.04)
    on = project(risky, gross, risk_charges=True)
    off = project(risky, gross, risk_charges=False)
    reference = project(clean, gross, risk_charges=True)
    assert on.fund[-1] < off.fund[-1]
    assert np.all(off.mortality == 0) and np.all(off.guarantee == 0)
    assert np.allclose(off.fund, project(clean, gross, risk_charges=False).fund, rtol=1e-14)
    assert on.mortality.sum() > reference.mortality.sum() > 0
    assert on.guarantee.sum() > 0


def test_exhausted_fund_scales_charges_and_never_goes_negative():
    case = plain_case(
        instalment=1.0,
        annualised_premium=1.0,
        schedule=schedule(admin=200.0),
    )
    path = project(case, Gross.of(0.04))
    assert path.fund.min() >= 0
    # The admin and mortality charges share the whole fund after allocation pro rata.
    assert path.admin[0] + path.mortality[0] == pytest.approx(0.95, rel=1e-12)
    assert path.admin[0] > 0 and path.mortality[0] > 0
    sar = 125_000 - (0.95 - 200.0)  # the cover less the fund left after the flat charge
    assert path.admin[0] / path.mortality[0] == pytest.approx(200.0 / (sar * 2.0 / 12000))
    assert path.admin[1:].sum() == 0 and path.fund.max() == 0


def test_gross_monthly_rate_is_the_scenario_library_flat_rate():
    from avk.esg.library import flat
    from avk.model.data import ScenarioSet

    base = ScenarioSet(
        variables={"ret_eq_large": np.zeros((1, 3))},
        ids=("1",),
        weights=np.array([1.0]),
        measure="deterministic",
        provenance={},
    )
    for annual in (0.04, 0.08):
        monthly = flat(base, ["ret_eq_large"], annual).variables["ret_eq_large"][0, 1]
        assert Gross.of(annual).monthly == monthly


# Reconciliation with the engine ---------------------------------------------------------

HISTORY = (
    "Premiums_Paid_To_Date",
    "Instalments_Paid",
    "PAC_To_Date",
    "Admin_To_Date",
    "MC_To_Date",
    "GC_To_Date",
    "Loyalty_To_Date",
    "PW_To_Date",
    "PW_Current_Year",
    "PW_Previous_Year",
    "FV_Sum_Current_Year",
    "Disc_Charge_Paid",
)
SCENARIOS = {
    "classic_annual": (0, {}),
    "wealth_monthly_early_loyalty": (
        1,
        {"V_loyalty_start_year": 2, "V_loyalty_requires_full_premiums": 0},
    ),
    "limited_pay_rebalance_escalation": (2, {}),
    "guarantee_charge_additions": (
        0,
        {
            "V_gmmb_on": 1,
            "V_gmmb_premium_multiple": 3.0,
            "V_guarantee_charge": 0.004,
            "V_guaranteed_addition_rate": 0.01,
            "V_loyalty_start_year": 3,
            "V_loyalty_requires_full_premiums": 0,
            "V_romc_fraction": 0.5,
            "V_ropac_fraction": 1.0,
        },
    ),
    "single_premium": (5, {}),
}


@pytest.mark.parametrize("annual", [0.04, 0.08])
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_projection_reconciles_with_the_engine_per_life(
    name, annual, ul_projection, projection_inputs
):
    index, overrides = SCENARIOS[name]
    report, _ = projection_inputs
    monthly = Gross.of(annual).monthly
    horizon = next(iter(report.scenarios.variables.values())).shape[1]
    fields = {
        "Duration_in_Months": 0,
        "V_pw_allowed": 0,
        **dict.fromkeys(HISTORY, 0),
        **{f"Fund_{k}_Value": 0.0 for k in range(1, 6)},
        **{f"Fund_{k}_Alpha": 0.0 for k in range(1, 6)},
        **overrides,
    }
    model, frame = ul_projection(
        index,
        scenario_overrides={
            f"ret_{asset}": np.full((1, horizon), monthly) for asset in ASSET_CLASSES
        },
        **fields,
    )
    row = frame.row(0, named=True)
    case = case_from_row(row, report.tables)
    path = project(case, Gross.of(annual), risk_charges=True)
    be = model["be"]
    months = case.months
    steps = slice(1, months + 1)
    for column, ours in {
        "fund_close_total": path.fund,
        "pac_pp": path.pac,
        "admin_pp": path.admin,
        "mc_pp": path.mortality,
        "gc_pp": path.guarantee,
        "fund_fmc_total": path.fmc,
        "loyalty_pp": path.loyalty,
        "booster_pp": path.booster,
        "guaranteed_addition_pp": path.guaranteed_addition,
        "tpp_pp": path.premiums_to_date,
        "sar": path.sum_at_risk,
    }.items():
        np.testing.assert_allclose(be(column)[steps], ours, rtol=1e-9, atol=1e-9, err_msg=column)
    values = year_end(path)
    fund = be("fund_close_total")
    for year in range(1, case.term_years + 1):
        step = 12 * year
        floor = be("floor_db")[step]
        if row["V_death_benefit_type"] == 1:
            engine = max(be("sa_eff")[step], floor, fund[step])
        else:
            engine = max(be("sa_eff")[step] + fund[step], floor)
        assert values.death_benefit[year - 1] == pytest.approx(engine, rel=1e-9)
    last = 12 * case.term_years
    roc, top_up = be("roc_pp")[last], be("gmmb_pp")[last]
    assert values.maturity_value[-1] == pytest.approx(fund[last] + roc + top_up, rel=1e-9)
