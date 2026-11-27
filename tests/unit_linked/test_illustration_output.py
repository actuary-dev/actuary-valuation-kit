"""The benefit illustration and the residual additions report."""

import numpy as np
import polars as pl
import pytest
from conftest import valid_book

from avk import api
from avk.cli import main
from avk.products.unit_linked.illustration import project, year_end
from avk.runs.ul_compliance import ILLUSTRATION_COLUMNS, case_from_row, library_gross
from avk.runtime.errors import InputError

RATES = (0.04, 0.08)


@pytest.fixture(scope="module")
def run_file(projection_inputs):
    return projection_inputs[0].config._path


@pytest.fixture(scope="module")
def breach_run(tmp_path_factory):
    """The six-policy book with UL6 (single premium) cut to 109,000, so its charges breach the
    caps from the seventh policy year and residual additions are needed."""
    from avk.demo.generate import generate

    path = generate(tmp_path_factory.mktemp("ul-breach"), "UNIT_LINKED", 6, 209)
    policies, holdings = valid_book()
    is_six = pl.col("Policy Number") == "UL6"
    policies = policies.with_columns(
        *(
            pl.when(is_six).then(value).otherwise(pl.col(name)).alias(name)
            for name, value in (
                ("Annualised Premium", 109_000.0),
                ("Premiums Paid To Date", 109_000.0),
                ("Sum Assured", 150_000.0),
            )
        )
    )
    holdings = holdings.with_columns(
        pl.when(pl.col("Policy Number") == "UL6")
        .then(109_000.0)
        .otherwise(pl.col("Premiums Allocated To Fund"))
        .alias("Premiums Allocated To Fund")
    )
    policies.write_csv(path.parent / "policies.csv")
    holdings.write_csv(path.parent / "policy_funds.csv")
    return path


def rows_of(report, number):
    frame = report.points.frame
    return frame.filter(pl.col("Policy_Number") == number).row(0, named=True)


def test_illustration_columns_and_year_end_values(run_file, projection_inputs, tmp_path):
    report = projection_inputs[0]
    result = api.ul_illustration(run_file, "UL1", output=tmp_path)
    table = result.table
    assert table.columns == list(ILLUSTRATION_COLUMNS)
    assert table.height == 2 * 20 and set(table["Gross_Return"]) == set(RATES)
    for rate in RATES:
        sub = table.filter(pl.col("Gross_Return") == rate).sort("Policy_Year")
        assert list(sub["Policy_Year"]) == list(range(1, 21))
        # An annual premium of 100,000 for 20 years; the charges that do not depend on the
        # fund (allocation, administration) are the same at both gross returns.
        assert (sub["Premiums_Paid"] == 100_000.0).all()
        other = table.filter(pl.col("Gross_Return") != rate).sort("Policy_Year")
        assert (
            sub["Premium_Allocation_Charge"].to_list()
            == other["Premium_Allocation_Charge"].to_list()
        )
        assert sub["Administration_Charge"].to_list() == other["Administration_Charge"].to_list()
        # Type I death benefit: the highest of cover, fund and 105% of the premiums paid.
        paid = np.cumsum(sub["Premiums_Paid"].to_numpy())
        expected = np.maximum(np.maximum(1_000_000.0, 1.05 * paid), sub["Fund_Value"].to_numpy())
        np.testing.assert_allclose(sub["Death_Benefit"].to_numpy(), expected, rtol=1e-12)
        # Maturity value only in the last year; surrender value none in it.
        assert sub["Maturity_Value"][:-1].is_null().all()
        assert sub["Maturity_Value"][-1] == pytest.approx(sub["Fund_Value"][-1], rel=1e-12)
        assert sub["Surrender_Value"][-1] is None
        # The first five years are inside the lock-in: the discontinuance charge is taken and
        # the proceeds are payable at its end (month 60).
        inside = sub.filter(pl.col("Policy_Year") <= 5)
        assert (inside["Surrender_Payable_Month"] == 60).all()
        pct = report.tables["ul_charge_scales/disc_pct_high"]
        cap = report.tables["ul_charge_scales/disc_cap_high"]
        column = list(pct.axes[1].keys).index(0)  # ULIP_CLASSIC is variant 0
        for row in inside.iter_rows(named=True):
            i = row["Policy_Year"] - 1
            charge = min(
                pct.values[i, column] * 100_000.0, row["Fund_Value"], cap.values[i, column]
            )
            assert row["Discontinuance_Charge"] == pytest.approx(charge, rel=1e-12)
            assert row["Surrender_Value"] == pytest.approx(row["Fund_Value"] - charge, rel=1e-12)
        later = sub.filter((pl.col("Policy_Year") > 5) & (pl.col("Policy_Year") < 20))
        np.testing.assert_allclose(
            later["Surrender_Value"].to_numpy(), later["Fund_Value"].to_numpy(), rtol=1e-14
        )
        assert list(later["Surrender_Payable_Month"]) == [12 * y for y in later["Policy_Year"]]
        # Net yield and RIY only from policy year 5, and they tie to the gross return.
        assert sub["RIY"][:4].is_null().all() and sub["RIY"][4:].is_not_null().all()
        measured = sub.filter(pl.col("Policy_Year") >= 5)
        np.testing.assert_allclose(
            measured["Net_Yield"].to_numpy() + measured["RIY"].to_numpy(), rate, atol=1e-14
        )
        assert (measured["RIY"] <= measured["RIY_Before_Additions"] + 1e-15).all()
    # Higher gross return, higher fund and higher fund management charge.
    low, high = (table.filter(pl.col("Gross_Return") == r).sort("Policy_Year") for r in RATES)
    assert (high["Fund_Value"] > low["Fund_Value"]).all()
    assert (high["Fund_Management_Charge"] > low["Fund_Management_Charge"]).all()
    assert pl.read_csv(result.files[0]).shape == table.shape
    assert result.files[0].name == "ul_illustration_UL1.csv"


def test_illustration_agrees_with_the_projection_of_the_policy(run_file, projection_inputs):
    report = projection_inputs[0]
    result = api.ul_illustration(run_file, "UL2")
    case = case_from_row(rows_of(report, "UL2"), report.tables)
    for rate in RATES:
        gross = library_gross(rate)
        ye = year_end(project(case, gross, risk_charges=True))
        sub = result.table.filter(pl.col("Gross_Return") == rate).sort("Policy_Year")
        np.testing.assert_allclose(sub["Fund_Value"].to_numpy(), ye.fund, rtol=1e-12)
        np.testing.assert_allclose(sub["Mortality_Charge"].to_numpy(), ye.mortality, rtol=1e-12)
        np.testing.assert_allclose(sub["Premiums_Paid"].to_numpy(), ye.premiums, rtol=1e-12)


def test_credited_additions_enter_the_illustrated_fund(breach_run):
    result = api.ul_illustration(breach_run, "UL6")
    report = api.check(breach_run)
    case = case_from_row(rows_of(report, "UL6"), report.tables)
    gross = library_gross(0.04)
    sub = result.table.filter(pl.col("Gross_Return") == 0.04).sort("Policy_Year")
    added = sub["Residual_Addition"].to_numpy()
    assert (added >= 0).all() and added.sum() > 0
    first = int(np.argmax(added > 0))
    assert first + 1 >= 6  # never before the sixth anniversary
    # In the first year with an addition the fund is the unaided fund plus the addition.
    bare = year_end(project(case, gross, risk_charges=True))
    assert sub["Fund_Value"][first] == pytest.approx(bare.fund[first] + added[first], rel=1e-12)
    # RIY after the addition is exactly the cap; before it the cap was breached.
    assert sub["RIY"][first] == pytest.approx(sub["RIY_Cap"][first], abs=1e-10)
    assert sub["RIY_Before_Additions"][first] > sub["RIY_Cap"][first]
    assert (sub["RIY"][5:] <= sub["RIY_Cap"][5:] + 1e-10).all()


def test_additions_report_per_policy_and_year(breach_run, tmp_path):
    result = api.ul_residual_additions(breach_run, output=tmp_path)
    table = result.table
    assert result.skipped == ("UL4", "UL5")  # discontinued and reduced paid-up policies
    assert set(table["Policy_Number"]) == {"UL1", "UL2", "UL3", "UL6"}
    assert (table["Residual_Addition"] >= 0).all()
    needed = table.filter(pl.col("Residual_Addition") > 0)
    assert "UL6" in set(needed["Policy_Number"])
    assert (needed["Policy_Year"] >= 6).all()
    # The report and the illustration solve the same additions.
    illustration = api.ul_illustration(breach_run, "UL6").table
    for rate in RATES:
        a = table.filter((pl.col("Policy_Number") == "UL6") & (pl.col("Gross_Return") == rate))
        b = illustration.filter(
            (pl.col("Gross_Return") == rate) & (pl.col("Policy_Year") >= 5)
        ).sort("Policy_Year")
        np.testing.assert_allclose(
            a.sort("Policy_Year")["Residual_Addition"].to_numpy(),
            b["Residual_Addition"].to_numpy(),
            rtol=1e-12,
        )
    assert pl.read_csv(tmp_path / "ul_residual_additions.csv").height == table.height
    one = api.ul_residual_additions(breach_run, policy="UL6").table
    assert set(one["Policy_Number"]) == {"UL6"}


def test_policies_that_are_not_premium_paying_are_rejected(run_file):
    for number, status in (("UL4", 1), ("UL5", 2)):
        with pytest.raises(InputError, match=f"{number}.*Policy Status {status}"):
            api.ul_illustration(run_file, number)
        with pytest.raises(InputError, match=number):
            api.ul_residual_additions(run_file, policy=number)
    with pytest.raises(InputError, match="unknown policy"):
        api.ul_illustration(run_file, "NOPE")
    with pytest.raises(InputError, match="unknown policy"):
        api.ul_residual_additions(run_file, policy="NOPE")


def test_command_line_illustration_and_additions(breach_run, tmp_path, capsys):
    code = main(
        ["ul", "illustration", str(breach_run), "--policy", "UL6", "--output", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert code == 0 and "UL6" in out and "maturity" in out and "4.00%" in out
    assert (tmp_path / "ul_illustration_UL6.csv").exists()
    code = main(["ul", "additions", str(breach_run), "--output", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0 and "need a residual addition" in out and "skipped" in out
    assert (tmp_path / "ul_residual_additions.csv").exists()
    assert main(["ul", "illustration", str(breach_run), "--policy", "UL4"]) == 1
    assert "InputError" in capsys.readouterr().err
