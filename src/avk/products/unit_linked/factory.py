"""Unit-linked definition-layer factory: loading specification, preparation, validation."""

from collections.abc import Mapping
from typing import Literal

import polars as pl

from avk.assumptions.context import AssumptionSpec, ScenarioVariable, declare
from avk.assumptions.models import (
    CommissionAssumption,
    InterestCurveAssumption,
    LapseAssumption,
    MortalityAssumption,
    TabularAssumption,
)
from avk.inputs.policies import ModelPointAdapter
from avk.model.data import Table
from avk.model.manifest import table_bindings
from avk.outputs.schema import CALENDAR, POLICY, STEP, OutputSchema
from avk.products.registry import ProductFactory
from avk.products.term.bindings import SEX
from avk.products.unit_linked import features
from avk.products.unit_linked.bindings import (
    ASSET_CLASSES,
    ASSET_RETURNS_TABLE,
    CAPS_TABLE,
    CHARGE_COLUMNS,
    CODE,
    COMMISSIONS_TABLE,
    DISC_CAPS_TABLE,
    FUNDS_TABLE,
    HOLDINGS_TABLE,
    LAPSE_TABLE,
    MORTALITY_CHARGES_TABLE,
    POLICY_TABLE,
    RIY_CAPS_TABLE,
    SCALES_TABLE,
    VARIANTS_TABLE,
    WITHDRAWALS_TABLE,
)
from avk.products.unit_linked.formulas import UnitLinked
from avk.products.unit_linked.output_columns import FUNDS
from avk.products.unit_linked.preparation import UnitLinkedModelPointAdapter, require_valuation
from avk.products.unit_linked.validation import UnitLinkedPolicyValidator
from avk.runtime.errors import ConfigError

SCENARIOS = (
    ScenarioVariable("roi", "interest_rates", "ROI", "lag", months=1),
    ScenarioVariable("vroi", "interest_rates", "VROI", "lag", months=1),
    ScenarioVariable(
        "reference_forward", "interest_rates", "Reference Forward Rates", "lag", months=1
    ),
    *(ScenarioVariable(f"ret_{a}", ASSET_RETURNS_TABLE, a, "lag", months=1) for a in ASSET_CLASSES),
)


class UnitLinkedTableAssumption(TabularAssumption):
    """The unit-linked keyed and year-key tables; field rules live in `features.py`."""

    kind: Literal["ul_keyed", "ul_year_key"]


def _names(rules: tuple[features.FieldRule, ...]) -> tuple[str, ...]:
    return tuple(rule.name for rule in rules)


class UnitLinkedFactory(ProductFactory):
    code = CODE
    policy_table = POLICY_TABLE
    companion_tables = (HOLDINGS_TABLE,)
    definition_class = UnitLinked
    parameter_column = CODE

    def definition(self, extensions: tuple[str, ...] = ()) -> type[UnitLinked]:
        if extensions:
            raise ConfigError(f"UNIT_LINKED extensions are not implemented: {extensions}")
        return self.definition_class

    def assumption_spec(self) -> AssumptionSpec:
        declared = table_bindings(self.definition_class)
        tables = {}
        for name, rules in (
            (FUNDS_TABLE, features.FUND_FIELDS),
            (VARIANTS_TABLE, features.VARIANT_FIELDS),
            (CAPS_TABLE, features.CAP_FIELDS),
        ):
            tables[name] = declare(
                declared,
                name,
                UnitLinkedTableAssumption,
                "ul_keyed",
                "mixed",
                columns=_names(rules),
                below="error",
                above="error",
            )
        for logical, rules in (
            (SCALES_TABLE, features.SCALE_FIELDS),
            (DISC_CAPS_TABLE, features.DISC_CAP_FIELDS),
        ):
            for rule in rules:
                name = f"{logical}/{rule.name}"
                tables[name] = declare(
                    declared,
                    name,
                    UnitLinkedTableAssumption,
                    "ul_year_key",
                    "mixed",
                    columns=(rule.name,),
                    logical_name=logical,
                )
        tables[RIY_CAPS_TABLE] = declare(
            declared,
            RIY_CAPS_TABLE,
            UnitLinkedTableAssumption,
            "ul_year_key",
            "mixed",
            columns=_names(features.RIY_FIELDS),
        )
        tables["mortality"] = declare(
            declared, "mortality", MortalityAssumption, "age_sex", "probability", columns=SEX
        )
        # Contractual charges per 1,000 of sum at risk: nonnegative amounts.
        tables[MORTALITY_CHARGES_TABLE] = declare(
            declared,
            MORTALITY_CHARGES_TABLE,
            MortalityAssumption,
            "age_sex",
            "amount",
            columns=CHARGE_COLUMNS,
        )
        for name, model in (
            (LAPSE_TABLE, LapseAssumption),
            (WITHDRAWALS_TABLE, LapseAssumption),
            (COMMISSIONS_TABLE, CommissionAssumption),
        ):
            tables[name] = declare(declared, name, model, "year_channel", "probability")
        for name, columns in (
            ("interest_rates", ("ROI", "VROI", "Reference Forward Rates")),
            (ASSET_RETURNS_TABLE, ASSET_CLASSES),
        ):
            tables[name] = declare(
                declared,
                name,
                InterestCurveAssumption,
                "annual_curve",
                "annual_effective",
                columns=columns,
                below="error",
                above="error",
            )
        return AssumptionSpec(self.code, tables, SCENARIOS, parameter_column=self.parameter_column)

    def model_point_adapter(self, tables: Mapping[str, Table]) -> ModelPointAdapter:
        """Product codes only: preparation needs the holdings (`companion_adapter`)."""
        return UnitLinkedModelPointAdapter(
            self.code, self.policy_table, tables, self.definition_class.FIELDS
        )

    def companion_adapter(
        self, tables: Mapping[str, Table], companions: Mapping[str, pl.DataFrame]
    ) -> ModelPointAdapter:
        return UnitLinkedModelPointAdapter(
            self.code,
            self.policy_table,
            tables,
            self.definition_class.FIELDS,
            companions[HOLDINGS_TABLE],
        )

    def output_schema(self, run_type: str) -> OutputSchema:
        """The skeleton's opening funds (basis-independent), keyed like Term."""
        require_valuation(run_type)
        return OutputSchema(
            entries=tuple((name, column, None) for name, column in FUNDS),
            keys=(
                ("Policy_Number", POLICY, None),
                ("Policy_Month", "policy_month", None),
                ("Calendar_Month", CALENDAR, None),
                ("Projection_Step", STEP, None),
            ),
            integer_keys=frozenset({"Policy_Month"}),
            seriatim=tuple((name, column, None, 0) for name, column in FUNDS),
        )

    def aggregate_ratios(self, schema: OutputSchema) -> dict[str, tuple[str, str, str, float]]:
        return {}

    def validator(self) -> UnitLinkedPolicyValidator:
        return UnitLinkedPolicyValidator(self.code)
