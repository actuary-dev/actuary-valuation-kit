"""Validate strategy schedules and resolve their static fields to policy slots."""

from collections.abc import Mapping

import numpy as np
import polars as pl

from avk.model.data import Table
from avk.products.unit_linked.bindings import MAX_FUND_SLOTS, POLICY_TABLE, STRATEGIES_TABLE
from avk.products.unit_linked.features import STRATEGY_FIELDS, check_rules

TARGETS = tuple(f"target_{k}" for k in range(1, MAX_FUND_SLOTS + 1))
STATIC_FIELDS = ("mode", "source_slot", "amount", *TARGETS)
EQUITY = ("eq_large", "eq_mid", "eq_small", "eq_global")
DEBT = ("gov_long", "gov_short", "corp_bond", "money_market")


def strategy_tables(tables: Mapping[str, Table]) -> dict[str, Table]:
    return {field.name: tables[f"{STRATEGIES_TABLE}/{field.name}"] for field in STRATEGY_FIELDS}


def check_strategies(tables: Mapping[str, Table]) -> list[str]:
    data = strategy_tables(tables)
    schedule = data["share"]
    if any(
        table.axes[1].keys != schedule.axes[1].keys or table.values.shape != schedule.values.shape
        for table in data.values()
    ):
        return [f"{STRATEGIES_TABLE}: all fields must use the same years and keys"]
    values = {name: table.values for name, table in data.items()}
    frame = pl.DataFrame({name: column.ravel() for name, column in values.items()})
    messages = check_rules(frame, STRATEGY_FIELDS, STRATEGIES_TABLE)
    if messages:
        return messages
    keys = schedule.axes[1].keys
    if 0 not in keys:
        messages.append(f"{STRATEGIES_TABLE}: strategy key 0 must exist")
    for i, key in enumerate(keys):
        row = {name: column[0, i] for name, column in values.items()}
        share = schedule.values[:, i]
        mode = row["mode"]
        name = f"{STRATEGIES_TABLE}: strategy {key}"
        if key == 0:
            if any((column[:, i] != 0).any() for column in values.values()):
                messages.append(f"{name} must have all fields zero")
            continue
        if mode == 0:
            messages.append(f"{name}: only key 0 may have mode 0")
        if any((values[field][:, i] != row[field]).any() for field in STATIC_FIELDS):
            messages.append(f"{name}: only share can vary by schedule year")
        slot = int(row["source_slot"])
        weights = [row[field] for field in TARGETS]
        if slot == 0 or weights[slot - 1] != 0 or abs(sum(weights) - 1) > 1e-12:
            messages.append(f"{name}: target weights must sum to 1 and exclude the source slot")
        if (mode == 1 and (np.diff(share) > 0).any()) or (mode == 2 and (np.diff(share) < 0).any()):
            messages.append(f"{name}: lifecycle equity share must decline toward maturity")
        if mode == 3 and ((share <= 0).any() or (share != share[0]).any()):
            messages.append(f"{name}: STP share must be positive and constant")
        if (mode == 4 and (row["amount"] <= 0 or (share != 0).any())) or (
            mode != 4 and row["amount"] != 0
        ):
            messages.append(f"{name}: only fixed-amount STP requires amount > 0 and share 0")
    return messages


def prepare_strategies(prepared: pl.DataFrame, tables: Mapping[str, Table]) -> pl.DataFrame:
    data = strategy_tables(tables)
    static = pl.DataFrame(
        {"Strategy_Id": data["mode"].axes[1].keys}
        | {f"Strategy_{field.title()}": data[field].values[0] for field in STATIC_FIELDS}
    )
    return prepared.join(static, on="Strategy_Id", how="left", maintain_order="left")


def strategy_policy_messages(prepared: pl.DataFrame) -> list[str]:
    if prepared["Strategy_Mode"].null_count():
        return [f"{POLICY_TABLE}: Fund Strategy must exist in {STRATEGIES_TABLE}"]
    strategies = prepared.filter(pl.col("Strategy_Mode") != 0)
    if strategies.is_empty():
        return []
    messages = []
    if (strategies["Policy_Status"] != 0).any():
        messages.append(f"{POLICY_TABLE}: Fund Strategy requires active Policy Status 0")
    lifecycle = pl.col("Strategy_Mode").is_in([1, 2])
    bad_slots = []
    for k in range(1, MAX_FUND_SLOTS + 1):
        source = pl.col("Strategy_Source_Slot") == k
        target = pl.col(f"Strategy_Target_{k}") > 0
        eq = pl.sum_horizontal(f"Fund_{k}_W_{asset}" for asset in EQUITY)
        debt = pl.sum_horizontal(f"Fund_{k}_W_{asset}" for asset in DEBT)
        bad_slots.append(
            ((source | target) & (pl.col(f"Fund_{k}_Selectable") != 1))
            | (lifecycle & ((source & (eq <= 0.5)) | (target & (debt <= 0.5))))
        )
    if strategies.filter(pl.any_horizontal(bad_slots)).height:
        messages.append(
            f"{POLICY_TABLE}: strategy source and targets must be held selectable funds "
            "with majority equity in the lifecycle source and majority debt in its targets"
        )
    return messages
