"""The cap test, the status rule and the residual addition, with hand-computed single
premium cases (no premium after the first, so the accumulated value is closed form)."""

import numpy as np
import pytest
from test_illustration import NO_FEATURES, plain_case, schedule

from avk.products.unit_linked.illustration import (
    FIRST_ADDITION_YEAR,
    FIRST_MEASUREMENT_YEAR,
    Gross,
    assess,
    project,
    riy,
)

GROSS = 0.08
YEAR_FACTOR = 1.08 * (1 - 0.0135)  # one policy year of fund growth after the FMC


def capped(*caps, **changes):
    """A single premium case whose cap is `caps` by year (the last repeats)."""
    base = schedule()
    sched = type(base)(**{**base.__dict__, "riy_cap": tuple(caps)})
    return plain_case(schedule=sched, **changes)


def test_first_years_and_measurement_points():
    assert FIRST_MEASUREMENT_YEAR == 5
    assert FIRST_ADDITION_YEAR == 6
    case = capped(0.04, term_years=12)
    measured = riy(project(case, Gross.of(GROSS), risk_charges=False))
    assert list(measured.years) == list(range(5, 13))


def test_a_compliant_design_passes_with_no_addition():
    case = capped(0.04)
    result = assess(case, Gross.of(GROSS))
    assert result.status == "pass"
    assert np.all(result.design.excess < 0)
    assert result.design.residual.sum() == 0
    assert result.with_additions.residual.sum() == 0
    assert result.worst_margin == pytest.approx(0.04 - result.design.riy.max(), abs=1e-15)


def test_addition_restores_the_cap_exactly_from_the_sixth_anniversary():
    """Caps of 4% to year 5 and 1% after: single premium 100,000 at 8% gross."""
    case = capped(0.04, 0.04, 0.04, 0.04, 0.04, 0.01, term_years=10)
    gross = Gross.of(GROSS)
    result = assess(case, gross)
    assert result.status == "pass_with_additions"
    design, added = result.design, result.with_additions
    assert list(design.years) == [5, 6, 7, 8, 9, 10]
    assert design.excess[0] < 0 < design.excess[1]  # year 5 passes by design, year 6 breaches
    # Year 6: the fund must accumulate the premium at 8% - 1% = 7%.
    stand_alone = 95_000.0 * YEAR_FACTOR**6
    wanted = 100_000.0 * 1.07**6
    assert added.residual[0] == 0  # nothing at year 5 (a design test)
    assert added.residual[1] == pytest.approx(wanted - stand_alone, rel=1e-12)
    # With the addition credited the measured net yield is exactly 7%: RIY equals the cap.
    assert added.riy[1] == pytest.approx(0.01, abs=1e-12)
    # Later years: the augmented fund grows by 1.0654... a year against the 7% target, so the
    # year 7 addition is smaller than the stand-alone shortfall, which ignores year 6's addition.
    stand_7 = 100_000.0 * 1.07**7 - 95_000.0 * YEAR_FACTOR**7
    assert 0 < added.residual[2] < stand_7
    assert np.all(added.residual >= 0)
    assert np.all(added.excess[1:] < 1e-12)
    # Every measured year after the first addition sits at the cap, never below it.
    assert np.allclose(added.riy[1:], 0.01, atol=1e-12)


def test_breach_before_the_first_addition_year_is_a_design_failure():
    case = capped(0.02, term_years=10)  # RIY at year 5 is about 2.55% against 2%
    result = assess(case, Gross.of(GROSS))
    assert result.status == "design_fail"
    assert result.first_breach_year == 5
    assert result.with_additions.residual[0] == 0  # year 5 is never repaired


def test_without_the_feature_a_late_breach_fails():
    features = {**NO_FEATURES, "single_premium": 1, "riy_additions_on": 0}
    case = capped(0.04, 0.04, 0.04, 0.04, 0.04, 0.01, term_years=10, features=features)
    result = assess(case, Gross.of(GROSS))
    assert result.status == "fail"
    assert result.first_breach_year == 6
    assert result.with_additions.residual.sum() == 0  # no addition is credited
    assert result.worst_margin < 0


def test_a_cap_of_one_never_binds():
    result = assess(capped(1.0), Gross.of(0.04))
    assert result.status == "pass"
    assert result.first_breach_year is None


def test_caps_repeat_beyond_the_end_of_the_table():
    case = capped(0.04, 0.03, term_years=9)
    measured = riy(project(case, Gross.of(GROSS), risk_charges=False))
    assert list(measured.cap) == [0.03] * 5  # years 5 to 9


def test_regular_premium_addition_hits_the_cap_by_an_independent_root():
    """Five annual instalments of 60,000 and a flat charge; a 1.5% cap from year 6."""
    base = schedule(pac=0.04, admin=90.0)
    sched = type(base)(**{**base.__dict__, "riy_cap": (0.04,) * 5 + (0.015,)})
    case = plain_case(
        term_years=10,
        payment_years=5,
        frequency=1,
        instalment=60_000.0,
        annualised_premium=60_000.0,
        instalments_payable=5,
        features=NO_FEATURES,
        fmcs=(0.01,),
        schedule=sched,
    )
    result = assess(case, Gross.of(0.06))
    assert result.status == "pass_with_additions"
    path = project(case, Gross.of(0.06), risk_charges=False, residual=True)
    for year in range(6, 11):
        coefficients = np.zeros(year + 1)
        coefficients[:5] = 60_000.0
        coefficients[-1] = -path.year_end(path.fund)[year - 1]
        roots = np.roots(coefficients)
        positive = roots[(np.abs(roots.imag) < 1e-9) & (roots.real > 0)].real
        assert len(positive) == 1
        measured = positive[0] - 1
        if path.year_end(path.residual)[year - 1] > 0:
            assert measured == pytest.approx(0.06 - 0.015, abs=1e-10)  # restored exactly
        else:
            assert measured >= 0.06 - 0.015 - 1e-10  # the fund is already above the cap
    assert path.year_end(path.residual)[5] > 0
