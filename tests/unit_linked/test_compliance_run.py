"""The pricing-time demonstration through the public API and the command line."""

import numpy as np
import polars as pl
import pytest

from avk import api
from avk.cli import main
from avk.products.unit_linked.illustration import Gross, assess
from avk.runs.ul_compliance import case_for_variant, library_gross
from avk.runtime.errors import InputError

VARIANTS = {
    "ULIP_CLASSIC",
    "ULIP_WEALTH_T2",
    "ULIP_MATURITY_GUARANTEE",
    "ULIP_SINGLE",
    "ULIP_LIMITED_PAY_ROC",
    "UL_INVESTMENT_BOND",
}


@pytest.fixture(scope="module")
def run_file(projection_inputs):
    return projection_inputs[0].config._path


def test_every_variant_is_tested_at_both_rates(run_file, tmp_path):
    result = api.ul_compliance(run_file, output=tmp_path)
    assert set(result.summary["Variant"]) == VARIANTS
    assert set(result.summary["Gross_Return"]) == {0.04, 0.08}
    assert set(result.variants["Variant"]) == VARIANTS
    assert {"Status_4pct", "Status_8pct"} <= set(result.variants.columns)
    # One summary row per variant, case and rate; each case has a row per measured year.
    keys = ["Variant", "Policy_Term", "Premium_Frequency", "Annualised_Premium", "Gross_Return"]
    assert result.summary.select(keys).is_duplicated().sum() == 0
    years = result.cases.group_by(keys).agg(
        pl.col("Policy_Year").min().alias("first"),
        pl.col("Policy_Year").max().alias("last"),
        pl.col("Policy_Year").n_unique().alias("n"),
    )
    joined = years.join(result.summary.select(keys), on=keys)
    assert joined.height == result.summary.height
    assert (joined["first"] == 5).all()
    assert (joined["last"] == joined["Policy_Term"]).all()
    assert (joined["n"] == joined["Policy_Term"] - 4).all()
    # The statuses of the rows agree with the flags of the cases.
    assert (result.cases["Within_Cap"] == (result.cases["Excess"] <= 1e-12)).all()
    assert (result.cases["Residual_Addition"] >= 0).all()


def test_uncapped_variant_passes_and_single_premium_has_one_mode(run_file):
    result = api.ul_compliance(run_file, terms=(10,))
    bond = result.summary.filter(pl.col("Variant") == "UL_INVESTMENT_BOND")
    assert set(bond["Status"]) == {"pass"}
    single = result.summary.filter(pl.col("Variant") == "ULIP_SINGLE")
    assert set(single["Premium_Frequency"]) == {0}
    regular = result.summary.filter(pl.col("Variant") == "ULIP_CLASSIC")
    assert set(regular["Premium_Frequency"]) == {1, 12}


def test_the_demonstration_is_deterministic_and_writes_readable_files(run_file, tmp_path):
    first = api.ul_compliance(run_file, terms=(10, 20), output=tmp_path / "a")
    second = api.ul_compliance(run_file, terms=(10, 20), output=tmp_path / "b")
    assert first.cases.equals(second.cases) and first.summary.equals(second.summary)
    assert [p.name for p in first.files] == [
        "ul_riy_cases.csv",
        "ul_riy_summary.csv",
        "ul_riy_variants.csv",
    ]
    for path, frame in zip(first.files, (first.cases, first.summary, first.variants), strict=True):
        read = pl.read_csv(path)
        assert read.columns == frame.columns and read.height == frame.height
    assert (tmp_path / "a" / "ul_riy_cases.csv").read_bytes() == (
        tmp_path / "b" / "ul_riy_cases.csv"
    ).read_bytes()


def test_options_choose_rates_premiums_and_fund(run_file):
    result = api.ul_compliance(
        run_file, rates=(0.06,), terms=(12,), frequencies=(4,), premiums=(1e6,), fund="EQ_INDEX"
    )
    assert set(result.summary["Gross_Return"]) == {0.06}
    assert set(result.summary["Annualised_Premium"]) == {1e6}
    assert set(result.summary["Fund"]) == {"EQ_INDEX"}
    assert set(result.summary.filter(pl.col("Variant") == "ULIP_CLASSIC")["Premium_Frequency"]) == {
        4
    }


def test_a_case_equals_the_single_case_assessment(run_file, projection_inputs):
    """The demonstration row is the assessment of the case built from the tables."""
    report = projection_inputs[0]
    result = api.ul_compliance(run_file, terms=(10,), frequencies=(1,), premiums=(100_000.0,))
    row = result.summary.filter(
        (pl.col("Variant") == "ULIP_CLASSIC") & (pl.col("Gross_Return") == 0.08)
    ).row(0, named=True)
    case = case_for_variant(
        report.tables,
        "ULIP_CLASSIC",
        term=10,
        frequency=1,
        annualised_premium=100_000.0,
        fund=row["Fund"],
    )
    expected = assess(case, library_gross(0.08))
    assert row["Status"] == expected.status
    assert row["Max_RIY"] == pytest.approx(float(np.max(expected.design.riy)), abs=1e-15)
    assert row["Worst_Margin"] == pytest.approx(expected.worst_margin, abs=1e-15)


def test_library_rates_equal_the_direct_monthly_equivalent():
    for annual in (0.04, 0.08, 0.1):
        assert library_gross(annual) == Gross.of(annual)


@pytest.mark.parametrize(
    "options",
    [
        {"rates": ()},
        {"rates": (0.04, 0.04)},
        {"rates": (-1.5,)},
        {"terms": (4,)},
        {"terms": ()},
        {"frequencies": (0,)},
        {"fund": "NO_SUCH_FUND"},
    ],
)
def test_bad_options_are_rejected(run_file, options):
    with pytest.raises(InputError):
        api.ul_compliance(run_file, **options)


def test_other_products_are_rejected(tmp_path):
    from avk.demo.generate import generate

    path = generate(tmp_path, "TERM", 6, 3)
    with pytest.raises(InputError, match="UNIT_LINKED"):
        api.ul_compliance(path)


def test_command_line_prints_each_variant_and_honours_strict(run_file, tmp_path, capsys):
    code = main(["ul", "compliance", str(run_file), "--terms", "10", "--output", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    for variant in VARIANTS:
        assert variant in out
    assert "4pct" in out and "8pct" in out and (tmp_path / "ul_riy_summary.csv").exists()
    args = ["ul", "compliance", str(run_file), "--terms", "10", "--premiums", "40000", "--strict"]
    assert main(args) == 1  # a small premium breaches the year-5 cap by design
    assert main(args[:-1]) == 0  # without --strict a failing result is still a result
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["ul", "compliance", str(run_file), "--rates", "x"])


def test_command_line_reports_errors_with_exit_code_one(tmp_path, capsys):
    from avk.demo.generate import generate

    path = generate(tmp_path, "TERM", 6, 3)
    assert main(["ul", "compliance", str(path)]) == 1
    assert "InputError" in capsys.readouterr().err
