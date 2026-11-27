import numpy as np
import pytest


@pytest.mark.parametrize(
    ("tail", "cte"),
    [
        ("upper", [[20.0, 5.0], [17.6, 5.0], [14.0, 3.75]]),
        ("lower", [[4.0, 0.0], [11.2, 3.0], [14.0, 3.75]]),
    ],
)
def test_weighted_distribution_uses_partial_tail_mass(tail, cte):
    from avk.runs.scenario_statistics import summarize

    # CTE levels .875, .375 and 0 select 12.5%, 62.5% and 100% of the mass.
    # For the lower tail of the first step the first 25% has value 4.
    values = np.array([[20.0, 0.0], [4.0, 5.0], [16.0, 5.0], [-300.0, 300.0]])
    weights = np.array([0.25, 0.25, 0.5, 0.0])
    actual = summarize(values, weights, (0.0, 0.25, 0.5, 1.0), (0.875, 0.375, 0.0), tail)
    np.testing.assert_allclose(
        actual, [[14.0, 3.75], [4.0, 0.0], [4.0, 0.0], [16.0, 5.0], [20.0, 5.0], *cte]
    )


def test_undefined_results_are_ignored_only_at_zero_probability():
    from avk.runs.scenario_statistics import summarize

    values = np.array([[2.0, np.inf], [4.0, 3.0], [np.nan, -np.inf]])
    actual = summarize(values, np.array([0.5, 0.5, 0.0]), (0.5,), (0.5,), "upper")
    np.testing.assert_array_equal(actual, [[3.0, np.nan], [2.0, np.nan], [4.0, np.nan]])


@pytest.mark.parametrize("weights", [[0.1] * 10, [0.1] * 8 + [0.075, 0.125]])
def test_percentile_includes_a_path_at_the_cumulative_probability_boundary(weights):
    from avk.runs.scenario_statistics import summarize

    values = np.arange(10, dtype=np.float64).reshape(-1, 1)
    assert summarize(values, np.array(weights), (0.8,), (), "upper")[1, 0] == 7.0
