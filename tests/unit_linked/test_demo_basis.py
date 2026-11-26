"""The invented unit-linked demo basis: formats, source scales, caps and shared files."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from avk.demo.generate import basis
from avk.inputs.formats import FormatSpec, read
from avk.inputs.registry import BUILTIN_FORMATS
from avk.model.data import Axis
from avk.products.unit_linked import features
from avk.products.unit_linked.bindings import ASSET_CLASSES, CHARGE_COLUMNS, PARAMETERS

RULE = Axis("binding", "int", 0, 0, "error", "error", (), None)
COMMITTED = Path(__file__).resolve().parents[2] / "examples/demo/basis"
UL_FILES = {
    "ul_funds.csv",
    "ul_variants.csv",
    "ul_regulatory_caps.csv",
    "ul_charge_scales.csv",
    "ul_disc_charge_caps.csv",
    "ul_riy_caps.csv",
    "mortality_charges_ul.csv",
    "lapse_rates_ul.csv",
    "partial_withdrawals_ul.csv",
    "commissions_ul.csv",
    "ul_asset_returns.csv",
}


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    path = tmp_path_factory.mktemp("ul-basis")
    basis(path)
    return path


def load(folder, name, columns, units="mixed"):
    spec = FormatSpec(name, {"path": name}, (RULE,), columns, "UNIT_LINKED", 480, units)
    return read(BUILTIN_FORMATS[name], pl.read_csv(folder / f"{name}.csv"), spec)


def names(rules):
    return tuple(rule.name for rule in rules)


def keyed_frame(table):
    return pl.DataFrame(
        {"key": list(table.axes[0].keys)}
        | {f: table.values[:, i] for i, f in enumerate(table.axes[1].keys)}
    )


def scale(folder, field):
    return load(folder, "ul_charge_scales", (field,))


def test_every_table_reads_and_obeys_its_rules(folder):
    for name, rules in (
        ("ul_funds", features.FUND_FIELDS),
        ("ul_variants", features.VARIANT_FIELDS),
        ("ul_regulatory_caps", features.CAP_FIELDS),
    ):
        table = load(folder, name, names(rules))
        assert features.check_rules(keyed_frame(table), rules, name) == []
    for name, rules in (
        ("ul_charge_scales", features.SCALE_FIELDS),
        ("ul_disc_charge_caps", features.DISC_CAP_FIELDS),
        ("ul_riy_caps", features.RIY_FIELDS),
    ):
        frame = pl.DataFrame({r.name: load(folder, name, (r.name,)).values.ravel() for r in rules})
        assert features.check_rules(frame, rules, name) == []
    assert load(folder, "mortality_charges_ul", CHARGE_COLUMNS, "amount").values.shape == (
        121,
        6,
    )
    for name in ("lapse_rates_ul", "partial_withdrawals_ul", "commissions_ul"):
        assert load(folder, name, ("rate",), "probability").values.shape == (40, 2)
    returns = load(folder, "ul_asset_returns", ASSET_CLASSES, "annual_effective")
    assert returns.values.shape == (40, 10)


def test_classic_scales_follow_the_source_product(folder):
    variants = keyed_frame(load(folder, "ul_variants", names(features.VARIANT_FIELDS)))
    classic = variants.filter(pl.col("key") == "ULIP_CLASSIC").row(0, named=True)
    column = scale(folder, "premium_allocation_rate").axes[1].keys.index(classic["variant_id"])
    expected = {
        "premium_allocation_rate": {1: 0.06, 2: 0.04, 4: 0.03, 6: 0.02, 10: 0.02, 11: 0.0},
        "admin_charge_monthly": {1: 200, 2: 200, 4: 200, 6: 150, 10: 150, 11: 100},
        "loyalty_rate": {1: 0, 2: 0, 4: 0, 6: 0, 10: 0.0025, 11: 0.003},
        "disc_pct_low": {1: 0.20, 2: 0.15, 4: 0.05, 6: 0, 10: 0, 11: 0},
        "disc_cap_low": {1: 3000, 2: 2000, 4: 1000, 6: 0, 10: 0, 11: 0},
        "disc_pct_high": {1: 0.06, 2: 0.04, 4: 0.02, 6: 0, 10: 0, 11: 0},
        "disc_cap_high": {1: 6000, 2: 5000, 4: 2000, 6: 0, 10: 0, 11: 0},
    }
    for field, values in expected.items():
        table = scale(folder, field)
        for year, value in values.items():
            assert table.values[year - 1, column] == pytest.approx(value, abs=1e-15), (field, year)
    assert classic["death_benefit_type"] == 1 and classic["loyalty_start_year"] == 10
    assert classic["lock_in_months"] == 60 and classic["revival_period_months"] == 36


def test_capped_variants_sit_within_caps(folder):
    variants = keyed_frame(load(folder, "ul_variants", names(features.VARIANT_FIELDS)))
    caps = keyed_frame(load(folder, "ul_regulatory_caps", names(features.CAP_FIELDS)))
    irdai = caps.filter(pl.col("key") == "IRDAI_2024").row(0, named=True)
    uncapped = caps.filter(pl.col("key") == "UNCAPPED").row(0, named=True)
    assert irdai["caps_apply"] == 1 and uncapped["caps_apply"] == 0
    disc_caps = {
        f: load(folder, "ul_disc_charge_caps", (f,)) for f in names(features.DISC_CAP_FIELDS)
    }
    capped = variants.filter(pl.col("regime_id") == irdai["regime_id"])
    assert capped.height == 5
    for row in capped.iter_rows(named=True):
        allocation = scale(folder, "premium_allocation_rate")
        column = allocation.axes[1].keys.index(row["variant_id"])
        pac = allocation.values[:, column]
        assert (pac <= irdai["pac_max"]).all()
        assert pac[:5].max() / pac[:5].min() <= irdai["pac_ratio_max_first5"]
        admin = scale(folder, "admin_charge_monthly").values[:, column]
        assert (admin <= irdai["admin_max_monthly"]).all()
        assert row["admin_escalation"] <= irdai["admin_escalation_max"]
        assert row["guarantee_charge"] <= irdai["guarantee_charge_max"]
        assert row["min_db_premium_multiple"] >= irdai["min_db_premium_multiple"]
        assert row["lock_in_months"] >= irdai["lock_in_months_min"]
        for field, cap in disc_caps.items():
            regime = cap.axes[1].keys.index(irdai["regime_id"])
            assert (scale(folder, field).values[:, column] <= cap.values[:, regime]).all()
    funds = keyed_frame(load(folder, "ul_funds", names(features.FUND_FIELDS)))
    selectable = funds.filter(pl.col("is_dpf") == 0)
    assert (selectable["fmc"] <= irdai["fmc_max"]).all()
    assert (funds.filter(pl.col("is_dpf") == 1)["fmc"] <= irdai["dpf_fmc_max"]).all()


def test_fund_universe(folder):
    funds = keyed_frame(load(folder, "ul_funds", names(features.FUND_FIELDS)))
    assert funds.height == 22
    dpf = funds.filter(pl.col("is_dpf") == 1)
    assert dpf["key"].to_list() == ["DPF"] and dpf["selectable"].to_list() == [0.0]
    weights = funds.select(f"w_{a}" for a in ASSET_CLASSES).to_numpy().sum(axis=1)
    np.testing.assert_allclose(weights, 1.0, rtol=0, atol=1e-12)
    assert set(funds.filter(pl.col("guarantee_type") > 0)["key"]) == {
        "GT_HIGHEST_NAV",
        "GT_CAPITAL_PROTECT",
    }
    assert ((funds["unit_price"] >= 10) & (funds["unit_price"] <= 80)).all()
    assert ((funds["alpha"] >= -0.005) & (funds["alpha"] <= 0.01)).all()


def test_unit_linked_parameters(folder):
    frame = pl.read_csv(folder / "product_parameters.csv")
    ul = frame.filter(pl.col("product") == "UNIT_LINKED")
    assert tuple(ul["parameter"]) == PARAMETERS


def assert_same_file(actual, expected):
    """As tests/regression/test_demo_inputs.py: the committed basis was generated on another
    platform, so values match within the parity decrement tolerance; keys, text and row
    order match exactly."""
    from avk.testing.parity import compare

    frame = pl.read_csv(expected, infer_schema_length=None)
    classes = {
        name: "decrement" if name == "value" and dtype.is_numeric() else "identifier"
        for name, dtype in frame.schema.items()
    }
    compare(actual, expected, classes=classes).assert_ok()


def test_shared_files_unchanged_for_existing_products(folder):
    generated = {p.name for p in folder.iterdir() if p.is_file()}
    committed = {p.name for p in COMMITTED.iterdir() if p.is_file()}
    assert generated - committed <= UL_FILES
    for name in sorted(committed - UL_FILES - {"product_parameters.csv"}):
        assert_same_file(folder / name, COMMITTED / name)
    old = pl.read_csv(COMMITTED / "product_parameters.csv").filter(
        pl.col("product") != "UNIT_LINKED"
    )
    new = pl.read_csv(folder / "product_parameters.csv")
    assert new.head(old.height).equals(old)
    assert set(new.tail(new.height - old.height)["product"]) == {"UNIT_LINKED"}
