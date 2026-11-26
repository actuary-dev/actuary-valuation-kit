"""The registered skeleton product: compile, check, run and the demo book."""

import json

import polars as pl
import pytest

from avk.cli import main
from avk.demo.generate import PRODUCTS, generate
from avk.demo.unit_linked import TABLES
from avk.products.registry import ProductRegistry
from avk.products.unit_linked import bindings, features, formulas
from avk.products.unit_linked.preparation import PREPARED_FIELDS
from avk.runs.check import check
from avk.runtime.errors import AvkError
from avk.testing.parity import compare


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    folder = tmp_path_factory.mktemp("ul-demo")
    return generate(folder, "UNIT_LINKED", 200, 209)


def test_formula_contract_matches_the_catalogue():
    assert formulas.ASSETS == bindings.ASSET_CLASSES
    assert formulas.SLOTS == bindings.MAX_FUND_SLOTS
    assert formulas.VARIANT_FEATURES == tuple(
        r.name for r in features.VARIANT_FIELDS if r.name not in ("variant_id", "regime_id")
    )
    assert formulas.UnitLinked.FIELDS == PREPARED_FIELDS
    assert formulas.UnitLinked.BASES == ("reserving", "be", "mc")
    assert formulas.UnitLinked.LABEL == "Unit-linked insurance"


def test_registered_with_companion_holdings():
    factory = ProductRegistry.default().for_code("UNIT_LINKED")
    assert factory.policy_table == "policies_ul"
    assert factory.companion_tables == ("policy_funds_ul",)
    assert PRODUCTS == (
        "TERM",
        "ACCIDENTAL_DEATH_RIDER",
        "CRITICAL_ILLNESS_RIDER",
        "DISABILITY_RIDER",
        "CREDIT_LIFE",
    )


def test_compile(capsys):
    assert main(["compile", "UNIT_LINKED"]) == 0
    assert "UNIT_LINKED" in capsys.readouterr().out


def test_demo_passes_check(demo):
    report = check(demo)
    assert report.points is not None and report.points.frame.height == 200
    assert set(report.contexts) == {"reserving", "be", "mc"}
    folder = demo.parent
    assert {p.name for p in folder.iterdir() if p.is_file()} == {
        "policies.csv",
        "policy_funds.csv",
        "valuation.json",
    }


def test_run_reports_the_opening_funds(demo, tmp_path):
    from avk.api import run

    run(demo)
    folder = demo.parent
    aggregate = pl.read_csv(folder / "output/valuation/UNIT_LINKED_Base_aggregate_output.csv")
    funds = pl.read_csv(folder / "basis/ul_funds.csv").filter(pl.col("field") == "unit_price")
    holdings = pl.read_csv(folder / "policy_funds.csv").join(
        funds.select(pl.col("key").alias("Fund Code"), pl.col("value").alias("price")),
        on="Fund Code",
    )
    expected = {
        name: float(
            holdings.filter(selector)
            .select((pl.col("Units") * pl.col("price")).sum())
            .item()
        )
        for name, selector in (
            ("funds_opening_unit_fund", pl.col("Fund Code") != "DPF"),
            ("funds_opening_dpf_fund", pl.col("Fund Code") == "DPF"),
        )
    }
    assert expected["funds_opening_dpf_fund"] > 0
    pl.DataFrame({"Projection_Step": [0], **{k: [v] for k, v in expected.items()}}).write_csv(
        tmp_path / "expected.csv"
    )
    aggregate.filter(pl.col("Projection_Step") == 0).write_csv(tmp_path / "actual.csv")
    classes = {"Projection_Step": "identifier", **dict.fromkeys(expected, "value")}
    compare(tmp_path / "actual.csv", tmp_path / "expected.csv", classes=classes).assert_ok()
    later = aggregate.filter(pl.col("Projection_Step") > 0)
    assert (later["funds_opening_unit_fund"] == 0).all()


@pytest.mark.parametrize("run_type", ["StressCapital", "IFRS17"])
def test_other_run_types_rejected(tmp_path, run_type):
    term = generate(tmp_path / "term", "TERM", 24, 209)
    source = json.loads(
        (term.parent / ("capital.json" if run_type == "StressCapital" else "measurement.json"))
        .read_text()
    )
    config = json.loads(generate(tmp_path / "ul", "UNIT_LINKED", 24, 209).read_text())
    config["Run_Type"] = run_type
    for key in ("Stress_Set", "IFRS17"):
        if key in source:
            config[key] = source[key]
    if run_type == "IFRS17":
        config["Inputs"]["Replace"]["locked"] = source["Inputs"]["Replace"]["locked"]
        config["Inputs"]["Replace"]["ifrs17_interest_rates"] = source["Inputs"]["Replace"][
            "ifrs17_interest_rates"
        ]
    path = tmp_path / "other.json"
    path.write_text(json.dumps(config))
    with pytest.raises(AvkError, match="UNIT_LINKED supports the Valuation run type only"):
        check(path)


def test_same_seed_is_byte_identical(tmp_path):
    first = generate(tmp_path / "a", "UNIT_LINKED", 60, 7).parent
    second = generate(tmp_path / "b", "UNIT_LINKED", 60, 7).parent
    for name in ("policies.csv", "policy_funds.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    for name in TABLES:
        assert (first / "basis" / f"{name}.csv").read_bytes() == (
            second / "basis" / f"{name}.csv"
        ).read_bytes()
    other = generate(tmp_path / "c", "UNIT_LINKED", 60, 8).parent
    assert (other / "policies.csv").read_bytes() != (first / "policies.csv").read_bytes()


def test_existing_products_configs_name_no_unit_linked_table(tmp_path):
    for product in PRODUCTS:
        config = json.loads(generate(tmp_path / product, product, 12, 209).read_text())
        assert not set(config["Inputs"]["Replace"]) & set(TABLES)
        assert "policy_funds_ul" not in config["Inputs"]["Replace"]


def streamed(demo, tmp_path, holdings=None):
    config = json.loads(demo.read_text())
    folder = demo.parent
    pl.read_csv(folder / "policies.csv").write_parquet(tmp_path / "policies.parquet")
    if holdings is not None:
        holdings.write_csv(tmp_path / "funds.csv")
        config["Inputs"]["Replace"]["policy_funds_ul"] = {"Path": str(tmp_path / "funds.csv")}
    config["Batch_Size"] = 2
    config["Inputs"]["Replace"]["policies_ul"] = {
        "Source": "parquet",
        "Path": str(tmp_path / "policies.parquet"),
    }
    path = tmp_path / "streamed.json"
    path.write_text(json.dumps(config))
    return path


def test_streamed_book_matches_csv(demo, tmp_path):
    whole = check(demo).points
    parts = check(streamed(demo, tmp_path)).points
    assert whole is not None and parts is not None
    whole.frame.select("Policy_Number", *PREPARED_FIELDS).write_csv(tmp_path / "whole.csv")
    parts.frame.select("Policy_Number", *PREPARED_FIELDS).write_csv(tmp_path / "parts.csv")
    classes = dict.fromkeys(("Policy_Number", *PREPARED_FIELDS), "identifier")
    compare(tmp_path / "parts.csv", tmp_path / "whole.csv", classes=classes).assert_ok()


def test_orphan_holdings_across_batches(demo, tmp_path):
    holdings = pl.read_csv(demo.parent / "policy_funds.csv")
    orphans = holdings.head(3).with_columns(
        pl.Series("Policy Number", ["GHOST1", "GHOST1", "GHOST2"])
    )
    path = streamed(demo, tmp_path, pl.concat([holdings, orphans]))
    with pytest.raises(AvkError) as info:
        check(path)
    assert str(info.value) == (
        "policy_funds_ul: 3 holding row(s) for 2 Policy Number(s) absent from policies_ul"
    )
