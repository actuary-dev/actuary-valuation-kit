"""Generate the repetitive UNIT_LINKED per-fund formulas and their totals."""

import argparse
import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = Path("src/avk/products/unit_linked/fund_slots.py")

SLOT = '''

    def fund_{k}_allocation(self, t):
        """Fund {k}'s share of the allocation weights."""
        return if_(
            self.allocation_total(t) > 0,
            self.policy.Fund_{k}_Allocation / self.allocation_total(t),
            0,
        )

    def fund_{k}_raw_open(self, t):
        """Opening active value of slot {k}, with rebalancing when due."""
        return if_(
            t == 0 or ((self.live(t) or self.maturity(t)) and self.A_begin(t) > 0),
            if_(
                self.rebalance(t),
                prev(self.fund_close_total, 0) * self.fund_{k}_allocation(t),
                prev(
                    self.fund_{k}_close,
                    self.policy.Fund_{k}_Value * (self.policy.Policy_Status == 0),
                ),
            ),
            0,
        )

    def fund_{k}_strategy_member(self, t):
        """Whether slot {k} belongs to the strategy basket."""
        return self.policy.Strategy_Source_Slot == {k} or self.policy.Strategy_Target_{k} > 0

    def fund_{k}_strategy_weight(self, t):
        """Lifecycle target weight within the equity and debt basket."""
        return if_(
            self.policy.Strategy_Source_Slot == {k},
            self.strategy_share(t),
            (1 - self.strategy_share(t)) * self.policy.Strategy_Target_{k},
        )

    def fund_{k}_strategy_change(self, t):
        """Gross lifecycle target minus the opening value in slot {k}."""
        return if_(
            self.lifecycle_switch(t) and self.fund_{k}_strategy_member(t),
            self.strategy_value(t) * self.fund_{k}_strategy_weight(t) - self.fund_{k}_raw_open(t),
            0,
        )

    def fund_{k}_switch_out(self, t):
        """Value sold from slot {k}, before the switch charge."""
        return if_(
            self.stp_switch(t) and self.policy.Strategy_Source_Slot == {k},
            if_(
                self.policy.Strategy_Mode == 3,
                self.fund_{k}_raw_open(t) * self.strategy_share(t),
                min(self.policy.Strategy_Amount, self.fund_{k}_raw_open(t)),
            ),
            max(-self.fund_{k}_strategy_change(t), 0),
        )

    def fund_{k}_switch_weight(self, t):
        """Share of net switch proceeds invested in slot {k}."""
        return if_(
            self.lifecycle_switch(t),
            if_(self.lifecycle_demand(t) > 0,
                max(self.fund_{k}_strategy_change(t), 0) / self.lifecycle_demand(t), 0),
            self.policy.Strategy_Target_{k},
        )

    def fund_{k}_open(self, t):
        """Opening slot value after internal strategy transfers and their charge."""
        return if_(
            self.switch_out_total(t) > 0,
            self.fund_{k}_raw_open(t) - self.fund_{k}_switch_out(t)
            + self.switch_net_pp(t) * self.fund_{k}_switch_weight(t),
            self.fund_{k}_raw_open(t),
        )

    def fund_{k}_after_premium(self, t):
        """Slot {k} after crediting its share of allocated premiums."""
        return self.fund_{k}_open(t) + self.allocated_pp(t) * self.fund_{k}_allocation(t)

    def fund_{k}_topup_raw_open(self, t):
        """Opening tagged top-up balance, including its share of any rebalance."""
        return if_(
            self.policy.V_topup_on and (t == 0 or self.A_begin(t) > 0),
            if_(
                self.rebalance(t),
                prev(self.topup_close_total, 0) * self.fund_{k}_allocation(t),
                prev(
                    self.fund_{k}_topup_close,
                    self.policy.Fund_{k}_Topup_Value * (self.policy.Policy_Status == 0),
                ),
            ),
            0,
        )

    def fund_{k}_topup_switch_out(self, t):
        """The portion of the sale made up of tagged top-up units."""
        return if_(
            self.fund_{k}_switch_out(t) > 0 and self.fund_{k}_raw_open(t) > 0,
            self.fund_{k}_switch_out(t)
            * (self.fund_{k}_topup_raw_open(t) / self.fund_{k}_raw_open(t)),
            0,
        )

    def fund_{k}_topup_open(self, t):
        """Opening tagged value after the same transfer and charge as other units."""
        return if_(
            self.switch_out_total(t) > 0 and self.policy.V_topup_on,
            self.fund_{k}_topup_raw_open(t) - self.fund_{k}_topup_switch_out(t)
            + self.switch_net_pp(t) * self.fund_{k}_switch_weight(t)
            * (self.topup_switch_out_total(t) / self.switch_out_total(t)),
            self.fund_{k}_topup_raw_open(t),
        )

    def fund_{k}_topup_after_premium(self, t):
        """Tagged top-up balance after buying new units."""
        return (
            self.fund_{k}_topup_open(t)
            + self.allocated_topup_pp(t) * self.fund_{k}_allocation(t)
        )

    def fund_{k}_withdrawable(self, t):
        """Slot value available for partial withdrawal."""
        return if_(
            self.topup_lock_active(t),
            max(self.fund_{k}_after_premium(t) - self.fund_{k}_topup_after_premium(t), 0),
            self.fund_{k}_after_premium(t),
        )

    def fund_{k}_withdrawal(self, t):
        """The withdrawal apportioned by the slot's unlocked holdings."""
        return if_(
            self.withdrawable_total(t) > 0,
            self.pw_pp(t) * (self.fund_{k}_withdrawable(t) / self.withdrawable_total(t)),
            0,
        )

    def fund_{k}_after_charges(self, t):
        """Slot {k} after its share of withdrawals and charges."""
        return if_(
            self.topup_lock_active(t),
            (self.fund_{k}_after_premium(t) - self.fund_{k}_withdrawal(t))
            * self.retention_after_withdrawal(t),
            self.fund_{k}_after_premium(t) * self.active_retention(t),
        )

    def fund_{k}_topup_after_charges(self, t):
        """Top-up units after deductions, valued at the opening price."""
        return self.fund_{k}_topup_after_premium(t) * if_(
            self.topup_lock_active(t), self.retention_after_withdrawal(t), self.active_retention(t)
        )

    def fund_{k}_market_return(self, t):
        """Monthly asset-mix return and fund alpha of slot {k}."""
        return ({asset_return}) + ((1 + self.policy.Fund_{k}_Alpha) ** (1 / 12) - 1)

    def fund_{k}_growth_rate(self, t):
        """Gross investment return for slot {k}."""
        return self.fund_{k}_market_return(t) * self.live(t)

    @on("reserving", overrides="fund_{k}_growth_rate")
    def fund_{k}_reserving_growth_rate(self, t):
        """Slot {k}'s return including the reserving margin."""
        return (
            (1 + self.fund_{k}_market_return(t)) * self.fund_return_factor(t) - 1
        ) * self.live(t)

    @on("mc", overrides="fund_{k}_growth_rate")
    def fund_{k}_mc_growth_rate(self, t):
        """Slot {k}'s certainty-equivalent or scenario-driven return."""
        return if_(
            self.mc_fund_return_source == 0,
            self.reference_forward[t],
            self.fund_{k}_market_return(t),
        ) * self.live(t)


    def fund_{k}_additions(self, t):
        """Slot {k}'s share of the active anniversary additions."""
        return self.additions_pp(t) * if_(
            self.fund_after_charges_total(t) > 0,
            self.fund_{k}_after_charges(t) / self.fund_after_charges_total(t),
            self.fund_{k}_allocation(t),
        )

    def fund_{k}_grown(self, t):
        """Active slot {k} after growth, before its fund management charge."""
        return (self.fund_{k}_after_charges(t) + self.fund_{k}_additions(t)) * (
            1 + self.fund_{k}_growth_rate(t)
        )

    def fund_{k}_fmc_rate(self, t):
        """Monthly fund management charge rate for slot {k}."""
        return (1 - (1 - self.policy.Fund_{k}_FMC) ** (1 / 12)) * self.live(t)

    def fund_{k}_fmc(self, t):
        """Fund management charge for active slot {k}."""
        return self.fund_{k}_grown(t) * self.fund_{k}_fmc_rate(t)

    def fund_{k}_close(self, t):
        """Closing active value of slot {k} before expected exits."""
        return self.fund_{k}_grown(t) - self.fund_{k}_fmc(t)

    def fund_{k}_topup_close(self, t):
        """Closing value of tagged top-up units before expected exits."""
        return self.fund_{k}_topup_after_charges(t) * (1 + self.fund_{k}_growth_rate(t)) * (
            1 - self.fund_{k}_fmc_rate(t)
        )

    def fund_{k}_highest_nav_on(self, t):
        """Whether slot {k} carries the variant's highest-NAV guarantee."""
        return (
            self.policy.V_highest_nav_start_month > 0
            and self.policy.Fund_{k}_Guarantee_Type == 1
        )

    def fund_{k}_nav_open(self, t):
        """Opening price per unit on this basis and scenario path."""
        return prev(self.fund_{k}_nav, self.policy.Fund_{k}_Unit_Price)

    def fund_{k}_nav(self, t):
        """Closing price per unit, with investment return net of FMC."""
        return if_(
            self.fund_{k}_highest_nav_on(t) or self.policy.V_topup_on,
            self.fund_{k}_nav_open(t)
            * (1 + self.fund_{k}_growth_rate(t))
            * (1 - self.fund_{k}_fmc_rate(t)),
            self.policy.Fund_{k}_Unit_Price,
        )

    def fund_{k}_topup_units(self, t):
        """Quantity of tagged top-up units held at month-end before exits."""
        return if_(self.fund_{k}_nav(t) > 0, self.fund_{k}_topup_close(t) / self.fund_{k}_nav(t), 0)

    def fund_{k}_highest_nav(self, t):
        """Highest unit price recorded in the contractual guarantee window."""
        return if_(
            self.fund_{k}_highest_nav_on(t),
            if_(
                self.live(t) and self.policy_month(t) >= self.policy.V_highest_nav_start_month,
                max(prev(self.fund_{k}_highest_nav, self.policy.Fund_{k}_Guaranteed_Price),
                    self.fund_{k}_nav(t)),
                prev(self.fund_{k}_highest_nav, self.policy.Fund_{k}_Guaranteed_Price),
            ),
            0,
        )

    def fund_{k}_nav_excess_per_unit(self, t):
        """The maturity-only shortfall per guaranteed unit."""
        return if_(
            self.maturity(t) and self.fund_{k}_highest_nav_on(t),
            max(self.fund_{k}_highest_nav(t) - self.fund_{k}_nav(t), 0),
            0,
        )

    def fund_{k}_nav_excess(self, t):
        """The shortfall on the active slot's units before expected maturity exits."""
        return if_(
            self.fund_{k}_nav_excess_per_unit(t) > 0 and self.fund_{k}_nav_open(t) > 0,
            self.fund_{k}_nav_excess_per_unit(t) * (
                (self.fund_{k}_after_charges(t) + self.fund_{k}_additions(t))
                / self.fund_{k}_nav_open(t)
            ),
            0,
        )
'''

RPU_SLOT = '''

    def rpu_{k}_open(self, t):
        """Opening aggregate paid-up holding in slot {k}."""
        return prev(
            self.rpu_{k}_close, self.policy.Fund_{k}_Value * (self.policy.Policy_Status == 2)
        )

    def rpu_{k}_after_charges(self, t):
        """Paid-up slot {k} after its proportional share of charges."""
        return self.rpu_{k}_open(t) * self.rpu_retention(t)

    def rpu_{k}_grown(self, t):
        """Paid-up slot {k} after its own investment return."""
        return self.rpu_{k}_after_charges(t) * (1 + self.fund_{k}_growth_rate(t))

    def rpu_{k}_fmc(self, t):
        """Fund management charge for paid-up slot {k}."""
        return self.rpu_{k}_grown(t) * self.fund_{k}_fmc_rate(t)

    def rpu_{k}_after_fmc(self, t):
        """Paid-up slot {k} after growth and all charges, before expected exits."""
        return self.rpu_{k}_grown(t) - self.rpu_{k}_fmc(t)

    def rpu_{k}_close(self, t):
        """Surviving paid-up slot {k} plus transfers from active units."""
        return (
            self.rpu_{k}_after_fmc(t) * self.R_survival(t)
            + self.to_rpu(t) * self.fund_{k}_close(t)
        )

    def rpu_{k}_nav_excess(self, t):
        """The shortfall on aggregate paid-up units before expected maturity exits."""
        return if_(
            self.fund_{k}_nav_excess_per_unit(t) > 0 and self.fund_{k}_nav_open(t) > 0,
            self.fund_{k}_nav_excess_per_unit(t)
            * (self.rpu_{k}_after_charges(t) / self.fund_{k}_nav_open(t)),
            0,
        )
'''

HEADER = '''"""Fund slot formulas generated by scripts/generate_ul_fund_slots.py."""

from avk.model.lang import Component, if_, int_axis, keymap, on, param, prev, scen, table

SLOTS = {count}


class FundSlots(Component):
    """Per-slot unit fund formulas and their policy totals."""

    REQUIRES = (
        "A_begin", "R_survival", "active_retention", "additions_pp", "allocated_pp",
        "live", "maturity", "rpu_retention", "to_rpu", "year_start",
        "allocated_topup_pp", "pw_pp", "retention_after_withdrawal", "topup_lock_active",
        "age", "policy_year", "policy_month",
    )
    fund_return_margin = param("fund_return_margin")
    mc_fund_return_source = param("mc_fund_return_source")
    reference_forward = scen("reference_forward")
{scenarios}
{static_strategies}
    strategy_share_data = table(
        "ul_strategies/share",
        axes=(
            int_axis("strategy_year", below="clamp", above="clamp"),
            keymap("Strategy_Id", unknown="error", above="error"),
        ),
    )

    def fund_return_factor(self, t):
        """Monthly factor for the signed reserving fund return margin."""
        return (1 + self.fund_return_margin) ** (1 / 12)

    def rebalance(self, t):
        """Rebalance at the start of the policy year when target weights exist."""
        return (
            self.policy.Strategy_Mode == 0
            and self.policy.V_auto_rebalance
            and self.year_start(t)
            and self.allocation_total(t) > 0
        )

    def lifecycle_switch(self, t):
        """Update lifecycle allocation at the first step and policy-year starts."""
        return (self.policy.Strategy_Mode == 1 or self.policy.Strategy_Mode == 2) and (
            (t == 1 or self.year_start(t)) and self.live(t) and self.A_begin(t) > 0
        )

    def stp_switch(self, t):
        """A monthly transfer while active and inside the term."""
        return self.policy.Strategy_Mode >= 3 and self.live(t) and self.A_begin(t) > 0

    def strategy_year(self, t):
        """The age or remaining-term index of the lifecycle schedule."""
        return if_(
            self.policy.Strategy_Mode == 1,
            self.age(t) + 1,
            if_(self.policy.Strategy_Mode == 2,
                self.policy.Policy_Term - self.policy_year(t) + 1, 1),
        )

    def strategy_share(self, t):
        """The lifecycle schedule at the current index or the level STP fraction."""
        return self.strategy_share_data[self.strategy_year(t), self.policy.Strategy_Id]

    def switch_charge_pp(self, t):
        """The charge funded from the month's gross internal switch."""
        return min(self.policy.V_switch_charge, self.switch_out_total(t))

    def switch_net_pp(self, t):
        """Proceeds of the month's switch available for reinvestment."""
        return self.switch_out_total(t) - self.switch_charge_pp(t)
'''

TOTALS = (
    ("nav_excess_A_pp", "self.fund_{k}_nav_excess(t)", "Highest-NAV excess per active life.", ""),
    (
        "nav_excess_R",
        "self.rpu_{k}_nav_excess(t)",
        "Highest-NAV excess on aggregate opening paid-up lives.",
        "",
    ),
    (
        "strategy_value",
        "self.fund_{k}_raw_open(t) * self.fund_{k}_strategy_member(t)",
        "Opening value within the strategy basket.",
        "",
    ),
    (
        "lifecycle_demand",
        "max(self.fund_{k}_strategy_change(t), 0)",
        "Gross lifecycle purchases requested.",
        "",
    ),
    ("switch_out_total", "self.fund_{k}_switch_out(t)", "Gross sales from all slots.", ""),
    (
        "topup_switch_out_total",
        "self.fund_{k}_topup_switch_out(t)",
        "Tagged portion of gross sales.",
        "",
    ),
    ("fund_fmc_total", "self.fund_{k}_fmc(t)", "Total active FMC per life.", ""),
    ("rpu_open_total", "self.rpu_{k}_open(t)", "Total paid-up funds at the open stage.", ""),
    ("rpu_fmc_total", "self.rpu_{k}_fmc(t)", "Total paid-up funds at the fmc stage.", ""),
    (
        "rpu_after_fmc_total",
        "self.rpu_{k}_after_fmc(t)",
        "Total paid-up funds at the after fmc stage.",
        "",
    ),
    ("rpu_close_total", "self.rpu_{k}_close(t)", "Total paid-up funds at the close stage.", ""),
    (
        "opening_unit_fund",
        "self.policy.Fund_{k}_Value",
        "All non-DPF holdings at valuation.",
        " * (t == 0)",
    ),
    (
        "allocation_total",
        "self.policy.Fund_{k}_Allocation",
        "Sum of policy allocation weights.",
        "",
    ),
    ("fund_open_total", "self.fund_{k}_open(t)", "Total active fund at the open stage.", ""),
    (
        "fund_after_premium_total",
        "self.fund_{k}_after_premium(t)",
        "Total active fund at the after premium stage.",
        "",
    ),
    (
        "fund_after_charges_total",
        "self.fund_{k}_after_charges(t)",
        "Total active fund at the after charges stage.",
        "",
    ),
    ("fund_close_total", "self.fund_{k}_close(t)", "Total active fund at the close stage.", ""),
    (
        "fund_growth_total",
        "(self.fund_{k}_after_charges(t) + self.fund_{k}_additions(t))"
        " * self.fund_{k}_growth_rate(t)",
        "Investment return credited to the active slots per life.",
        "",
    ),
    (
        "rpu_growth_total",
        "self.rpu_{k}_after_charges(t) * self.fund_{k}_growth_rate(t)",
        "Investment return credited to the opening paid-up slots.",
        "",
    ),
    ("topup_close_total", "self.fund_{k}_topup_close(t)", "Total tagged top-up fund at close.", ""),
    (
        "withdrawable_total",
        "self.fund_{k}_withdrawable(t)",
        "Unlocked active funds after premium.",
        "",
    ),
)


def render(count: int, assets: tuple[str, ...]) -> str:
    slots = range(1, count + 1)
    scenarios = "\n".join(f'    ret_{asset} = scen("ret_{asset}")' for asset in assets)
    static_fields = ("mode", "source_slot", "amount", *(f"target_{k}" for k in slots))
    static_strategies = "\n".join(
        f'    strategy_{name}_data = table("ul_strategies/{name}", axes=())'
        for name in static_fields
    )
    source = HEADER.format(count=count, scenarios=scenarios, static_strategies=static_strategies)
    for k in slots:
        asset_return = " + ".join(
            f"self.policy.Fund_{k}_W_{asset} * self.ret_{asset}[t]" for asset in assets
        )
        source += SLOT.format(k=k, asset_return=asset_return) + RPU_SLOT.format(k=k)
    for name, term, doc, factor in TOTALS:
        total = " + ".join(term.format(k=k) for k in slots)
        source += f'''
    def {name}(self, t):
        """{doc}"""
        return ({total}){factor}
'''
    result = subprocess.run(
        ["ruff", "format", "--stdin-filename", str(MODULE), "-"],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / MODULE
    bindings = runpy.run_path(str(target.with_name("bindings.py")))
    expected = render(bindings["MAX_FUND_SLOTS"], bindings["ASSET_CLASSES"])
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            print(
                f"{MODULE.as_posix()} is stale. "
                "Run uv run python scripts/generate_ul_fund_slots.py."
            )
            return 1
        print(f"{MODULE.as_posix()} is current.")
    else:
        target.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
