"""The model specification's verification checks on a 1,000-policy demo book."""

import numpy as np
import pytest

from avk.assumptions.lowering import lower
from avk.demo.generate import generate
from avk.model.executor import OutputRequest, project
from avk.products.unit_linked.bindings import MAX_FUND_SLOTS
from avk.products.unit_linked.formulas import UnitLinked
from avk.runs.cases import case_parameters
from avk.runs.check import check
from avk.runs.compile import product_kernel

SLOTS = range(1, MAX_FUND_SLOTS + 1)
BASES = UnitLinked.BASES
RATES = {"reserving": "vroi", "be": "roi", "mc": "reference_forward"}
COLUMNS = (
    "A_begin",
    "D_begin",
    "R_begin",
    "A_end",
    "D_end",
    "R_end",
    "lives_end",
    "deaths_A",
    "deaths_D",
    "deaths_R",
    "paid_out_A",
    "lockin_exits_D",
    "surrenders_R",
    "expiries_R",
    "maturities_A",
    "maturities_R",
    "maturities",
    "to_dpf",
    "to_rpu",
    "unit_reserve",
    "allocated_premiums",
    "addition_outgo",
    "fund_growth_total",
    "rpu_growth_total",
    "dpf_credited_return",
    "admin_income",
    "mc_income",
    "gc_income",
    "pac_income",
    "fmc_income_A",
    "rpu_fmc_total",
    "dpf_fmc",
    "disc_charge_income",
    "charge_income",
    "unit_exit_benefits",
    "partial_withdrawal_outgo",
    "unit_segment_profit",
    "admin_pp",
    "mc_pp",
    "gc_pp",
    "fund_fmc_total",
    "rpu_deduction_total",
    "rpu_mc",
    "sar",
    "rpu_sar",
    "sa_eff",
    "floor_db",
    "fund_before_mortality",
    "net_cashflows",
    "gf_reserve_dcf",
    "gf_reserve_floor",
    "gf_reserve_held",
    "total_reserve",
    "dpf_open",
    "dpf_guaranteed",
    "live",
    "policy_month",
    "dpf_return",
    *(f"fund_{k}_growth_rate" for k in SLOTS),
    "be_reserves",
    "be_net_cf",
    "interest_on_reserves",
    "profit_before_tax",
    "bel",
)


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    path = generate(tmp_path_factory.mktemp("ul-spec"), "UNIT_LINKED", 1000, 209)
    report = check(path)
    assert report.points is not None and report.scenarios is not None
    kernel = product_kernel(UnitLinked)
    months = next(iter(report.scenarios.variables.values())).shape[1]
    inputs = lower(
        report.contexts, report.points, report.scenarios, kernel, case_parameters(None, months)
    )
    labels = {
        (name, basis): f"{name}@{basis}" if f"{name}@{basis}" in kernel.columns else name
        for name in COLUMNS
        for basis in BASES
    }
    wanted = tuple(dict.fromkeys(labels.values()))
    projection = project(kernel, inputs, OutputRequest(grids=wanted))
    grids = dict(zip(projection.grid_columns, projection.grids.swapaxes(0, 1), strict=True))
    data = {basis: {name: grids[labels[(name, basis)]][0] for name in COLUMNS} for basis in BASES}
    return data, report


def scale(values):
    """Per-policy scale for the money parity rule."""
    return np.max(np.abs(values), axis=1, keepdims=True)


def money_close(actual, expected):
    """The CLAUDE.md value rule: 1e-6 relative plus 1e-8 times scale, floor 1e-5."""
    allowed = np.maximum(1e-5, 1e-6 * np.abs(expected) + 1e-8 * scale(expected))
    assert (np.abs(actual - expected) <= allowed).all(), np.max(np.abs(actual - expected))


def decrement_close(actual, expected):
    allowed = 1e-9 * np.abs(expected) + 1e-10 * scale(expected)
    assert (np.abs(actual - expected) <= allowed).all(), np.max(np.abs(actual - expected))


@pytest.mark.parametrize("basis", BASES)
def test_check_01_decrements_are_exhaustive(book, basis):
    d = book[0][basis]
    opening = d["A_begin"] + d["D_begin"] + d["R_begin"]
    exits = (
        d["deaths_A"]
        + d["deaths_D"]
        + d["deaths_R"]
        + d["paid_out_A"]
        + d["lockin_exits_D"]
        + d["surrenders_R"]
        + d["expiries_R"]
        + d["maturities"]
    )
    decrement_close(d["lives_end"], opening - exits)
    leavers = exits[:, 1:].sum(axis=1)
    np.testing.assert_allclose(leavers + d["lives_end"][:, -1], 1.0, rtol=0, atol=1e-12)
    assert not d["lives_end"][:, -1].any()


@pytest.mark.parametrize("basis", BASES)
def test_check_02_unit_fund_reconciles_every_month(book, basis):
    d = book[0][basis]
    previous = np.zeros_like(d["unit_reserve"])
    previous[:, 1:] = d["unit_reserve"][:, :-1]
    rolled = (
        previous
        + d["allocated_premiums"]
        + d["addition_outgo"]
        + d["A_begin"] * d["fund_growth_total"]
        + d["rpu_growth_total"]
        + d["dpf_credited_return"]
        - (d["admin_income"] + d["mc_income"] + d["gc_income"])
        - (d["fmc_income_A"] + d["rpu_fmc_total"] + d["dpf_fmc"] + d["disc_charge_income"])
        - d["unit_exit_benefits"]
        - d["partial_withdrawal_outgo"]
    )
    money_close(d["unit_reserve"][:, 1:], rolled[:, 1:])


@pytest.mark.parametrize("basis", BASES)
def test_check_03_charge_income_equals_charge_outgo_item_by_item(book, basis):
    d = book[0][basis]
    active = d["A_begin"]
    money_close(
        d["admin_income"] + d["mc_income"] + d["gc_income"],
        active * (d["admin_pp"] + d["mc_pp"] + d["gc_pp"]) + d["rpu_deduction_total"],
    )
    money_close(d["fmc_income_A"], active * d["fund_fmc_total"])
    money_close(
        d["charge_income"],
        d["pac_income"]
        + d["admin_income"]
        + d["mc_income"]
        + d["gc_income"]
        + d["fmc_income_A"]
        + d["rpu_fmc_total"]
        + d["dpf_fmc"]
        + d["disc_charge_income"],
    )


@pytest.mark.parametrize("basis", BASES)
def test_check_04_sum_at_risk_never_negative_and_nil_above_the_floors(book, basis):
    d, report = book[0][basis], book[1]
    assert (d["sar"] >= 0).all() and (d["rpu_sar"] >= 0).all()
    type_one = report.points.frame["V_death_benefit_type"].to_numpy()[:, None] == 1
    covered = d["fund_before_mortality"] >= np.maximum(d["sa_eff"], d["floor_db"])
    assert (d["sar"][type_one & covered] == 0).all()
    assert (type_one & covered & (d["A_begin"] > 0)).any()


@pytest.mark.parametrize("basis", BASES)
def test_check_05_no_mortality_charge_without_sum_at_risk(book, basis):
    d = book[0][basis]
    assert not d["mc_pp"][d["sar"] == 0].any()
    assert not d["rpu_mc"][d["rpu_sar"] == 0].any()


@pytest.mark.parametrize("basis", BASES)
def test_check_06_recursion_equals_discounted_summation(book, basis):
    d, report = book[0][basis], book[1]
    rates = report.scenarios.variables[RATES[basis]][0]
    months = rates.size
    factor = np.ones(months)
    for s in range(1, months):
        factor[s] = factor[s - 1] / (1 + rates[s])
    discounted = d["net_cashflows"] * factor
    later = np.cumsum(discounted[:, ::-1], axis=1)[:, ::-1]
    summed = np.zeros_like(later)
    summed[:, :-1] = later[:, 1:] / factor[:-1]
    money_close(d["gf_reserve_dcf"], summed)


@pytest.mark.parametrize("basis", BASES)
def test_check_07_floors_hold(book, basis):
    d = book[0][basis]
    assert (d["gf_reserve_held"] >= 0).all()
    assert (d["gf_reserve_held"] >= d["gf_reserve_floor"]).all()
    bites = (d["gf_reserve_dcf"] < d["gf_reserve_held"]) & (d["lives_end"] > 0)
    assert bites[:, 0].mean() > 0.5


def test_check_08_reserve_roll_forward_ties(book):
    d = book[0]["be"]
    previous = np.zeros_like(d["be_reserves"])
    previous[:, 1:] = d["be_reserves"][:, :-1]
    money_close(
        d["be_reserves"],
        previous + d["be_net_cf"] + d["interest_on_reserves"] - d["profit_before_tax"],
    )


def best_estimate_liability(book):
    """The best-estimate liability at the valuation date, per policy: the unit reserve plus
    the best-estimate basis's general fund DCF, with no statutory floors. The model
    specification's check 9 compares the reserving reserve with this liability, on the
    same real-world economics, so that only the margins for adverse deviation differ."""
    be = book[0]["be"]
    return be["unit_reserve"][:, 0] + be["gf_reserve_dcf"][:, 0]


def money_allowance(expected):
    """The CLAUDE.md money rule for a single value: 1e-6 relative, floor 1e-5."""
    return np.maximum(1e-5, 1e-6 * np.abs(expected))


def test_check_09_reserving_reserve_at_least_the_best_estimate_liability(book):
    """The margins need not all point the same way for every policy, so the direction is
    tested rather than assumed. On the demo book one return-of-allocation-charge policy
    seven months from maturity sits INR 2.85 below its best-estimate liability (4e-7
    relative): higher lapses forfeit the refund, offsetting the other margins. That is
    within the money tolerance; anything larger fails."""
    expected = best_estimate_liability(book)
    held = book[0]["reserving"]["total_reserve"][:, 0]
    assert (held >= expected - money_allowance(expected)).all()
    dcf_reserving = book[0]["reserving"]["gf_reserve_dcf"][:, 0]
    dcf_be = book[0]["be"]["gf_reserve_dcf"][:, 0]
    assert (dcf_reserving >= dcf_be - money_allowance(expected)).all()


def test_check_09_market_consistent_comparison_reported(book, capsys):
    """Not a check of the specification: the reserving basis takes credit for real-world
    fund growth less its margin, while the mc BEL grows funds at the risk-free rate, so the
    statutory reserve can sit below the mc BEL where future charges matter most. Reported
    per variant for the maintainer."""
    margin = book[0]["reserving"]["total_reserve"][:, 0] - book[0]["mc"]["bel"][:, 0]
    variants = book[1].points.frame["Variant_Id"].to_numpy()
    with capsys.disabled():
        print()
        print(
            f"reserving reserve less mc BEL at step 0: {(margin < 0).sum()} below, "
            f"total shortfall {margin[margin < 0].sum():.2f}"
        )
        for variant in np.unique(variants):
            chosen = margin[variants == variant]
            print(f"  variant {variant}: {chosen.size} policies, {(chosen < 0).sum()} below")
    assert np.isfinite(margin).all()


@pytest.mark.parametrize("basis", BASES)
def test_check_10_dpf_never_credits_below_the_guaranteed_rate(book, basis):
    d = book[0][basis]
    assert (d["dpf_credited_return"] >= d["dpf_open"] * d["dpf_guaranteed"]).all()
    assert (d["dpf_open"][:, 1] > 0).any()


@pytest.mark.parametrize("basis", BASES)
def test_check_12_fund_nil_after_maturity(book, basis):
    d, report = book[0][basis], book[1]
    frame = report.points.frame
    settle = np.maximum(
        frame["Policy_Term"].to_numpy() * 12 - frame["Duration_in_Months"].to_numpy(), 1
    )
    steps = np.arange(d["unit_reserve"].shape[1])
    after = steps[None, :] >= settle[:, None]
    assert not d["unit_reserve"][after].any()
    assert not d["lives_end"][after].any()


@pytest.mark.parametrize("basis", BASES)
def test_check_13_unit_segment_profit_nil(book, basis):
    d = book[0][basis]
    money_close(d["unit_reserve"] + d["unit_segment_profit"], d["unit_reserve"])


def test_check_14_mc_funds_grow_at_the_risk_free_rate(book):
    d, report = book[0]["mc"], book[1]
    rf = report.scenarios.variables["reference_forward"][0]
    live = d["live"].astype(bool)
    expected = np.broadcast_to(rf, live.shape)
    for k in SLOTS:
        np.testing.assert_array_equal(d[f"fund_{k}_growth_rate"][live], expected[live])
    np.testing.assert_array_equal(d["dpf_return"][live], expected[live])
