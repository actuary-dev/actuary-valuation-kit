"""Unit-linked constants and the field catalogue."""

import polars as pl
import pytest

from avk.products.unit_linked import bindings, features
from avk.products.unit_linked.features import FieldRule, check_rules


def test_constants():
    assert bindings.ASSET_CLASSES == (
        "eq_large",
        "eq_mid",
        "eq_small",
        "eq_global",
        "gov_long",
        "gov_short",
        "corp_bond",
        "money_market",
        "gold",
        "real_assets",
    )
    assert tuple("ret_" + a for a in bindings.ASSET_CLASSES) == bindings.SCENARIO_ASSETS
    assert bindings.MAX_FUND_SLOTS == 5
    assert (bindings.STATUS_ACTIVE, bindings.STATUS_DPF, bindings.STATUS_RPU) == (0, 1, 2)
    assert (bindings.POLICY_TABLE, bindings.HOLDINGS_TABLE) == ("policies_ul", "policy_funds_ul")
    assert bindings.CODE == "UNIT_LINKED"


def test_fund_fields_carry_every_asset_weight():
    names = [rule.name for rule in features.FUND_FIELDS]
    for asset in bindings.ASSET_CLASSES:
        assert f"w_{asset}" in names
    assert {"unit_price", "fmc", "alpha", "selectable", "is_dpf", "guarantee_type"} <= set(names)
    assert "risk_class" in names


@pytest.mark.parametrize(
    "rules",
    [
        features.VARIANT_FIELDS,
        features.FUND_FIELDS,
        features.CAP_FIELDS,
        features.SCALE_FIELDS,
        features.DISC_CAP_FIELDS,
        features.RIY_FIELDS,
    ],
)
def test_rule_names_unique(rules):
    names = [rule.name for rule in rules]
    assert len(names) == len(set(names))
    assert all(isinstance(rule, FieldRule) for rule in rules)


def test_variant_fields_exact():
    assert [r.name for r in features.VARIANT_FIELDS] == [
        "variant_id",
        "regime_id",
        "single_premium",
        "death_benefit_type",
        "min_db_premium_multiple",
        "lock_in_months",
        "dpf_enabled",
        "rpu_mode",
        "revival_period_months",
        "pw_allowed",
        "pw_start_year",
        "pw_reduces_sa",
        "loyalty_on",
        "loyalty_basis",
        "loyalty_start_year",
        "loyalty_requires_full_premiums",
        "guaranteed_addition_rate",
        "romc_fraction",
        "ropac_fraction",
        "roadmin_fraction",
        "gmmb_on",
        "gmmb_premium_multiple",
        "guarantee_charge",
        "admin_escalation",
        "mortality_charge_multiplier",
        "disc_ap_threshold",
        "auto_rebalance",
        "riy_additions_on",
    ]


RULES = (
    FieldRule("flag", "flag", frozenset({0.0, 1.0}), None, None, False),
    FieldRule("months", "int", None, 1.0, None, False),
    FieldRule("rate", "rate", None, 0.0, 1.0, True),
    FieldRule("price", "amount", None, 0.0, None, False, minimum_open=True),
)


def frame(**overrides):
    values = {"flag": 1.0, "months": 1.0, "rate": 0.0, "price": 0.01, **overrides}
    return pl.DataFrame({k: [v] for k, v in values.items()})


def test_check_rules_accepts_boundaries():
    assert check_rules(frame(), RULES, "t") == []
    assert check_rules(frame(rate=0.999999, flag=0.0), RULES, "t") == []


@pytest.mark.parametrize(
    ("column", "value", "fragment"),
    [
        ("flag", 2.0, "t: flag must be one of [0, 1]"),
        ("months", 0.0, "t: months must be at least 1"),
        ("months", 1.5, "t: months must be an integer"),
        ("rate", 1.0, "t: rate must be below 1"),
        ("rate", -0.1, "t: rate must be at least 0"),
        ("price", 0.0, "t: price must exceed 0"),
        ("rate", float("nan"), "t: rate must be finite"),
    ],
)
def test_check_rules_flags_violations(column, value, fragment):
    messages = check_rules(frame(**{column: value}), RULES, "t")
    assert any(fragment in m for m in messages), messages


def test_check_rules_missing_column():
    messages = check_rules(frame().drop("rate"), RULES, "t")
    assert messages == ["t: missing field rate"]


def test_check_rules_closed_maximum():
    rule = FieldRule("x", "rate", None, 0.0, 1.0, False)
    assert check_rules(pl.DataFrame({"x": [1.0]}), (rule,), "t") == []
    assert check_rules(pl.DataFrame({"x": [1.01]}), (rule,), "t") == ["t: x must be at most 1"]
