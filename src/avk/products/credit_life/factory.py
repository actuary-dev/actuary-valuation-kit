"""Stateless CREDIT_LIFE factory, preparation and the Valuation output schema."""

from collections.abc import Mapping

from avk.assumptions.context import AssumptionSpec, declare
from avk.assumptions.models import (
    CommissionAssumption,
    ExpenseAssumption,
    InterestCurveAssumption,
    LapseAssumption,
    MortalityAssumption,
)
from avk.inputs.policies import ModelPointAdapter
from avk.model.data import Table
from avk.model.manifest import table_bindings
from avk.outputs.schema import CALENDAR, POLICY, STEP, OutputSchema
from avk.products.credit_life.formulas import CreditLife, IfrsCreditLife
from avk.products.credit_life.output_columns import CASHFLOWS, EXITS
from avk.products.credit_life.preparation import (
    CreditLifeModelPointAdapter,
    CreditLifePolicyValidator,
)
from avk.products.registry import ProductFactory
from avk.products.term.bindings import IFRS_SCHEDULES, INITIAL, RENEWAL, SEX
from avk.products.term.factory import SCENARIOS
from avk.products.term.output_columns import BE_LAYER, PRESENT_VALUES
from avk.runtime.errors import ConfigError


class CreditLifeFactory(ProductFactory):
    code, policy_table = "CREDIT_LIFE", "policies_credit_life"
    definition_class = CreditLife
    measurement = False

    def definition(self, extensions: tuple[str, ...] = ()) -> type[CreditLife]:
        if extensions:
            raise ConfigError(f"CREDIT_LIFE extensions are not implemented: {extensions}")
        return self.definition_class

    def assumption_spec(self) -> AssumptionSpec:
        declared = table_bindings(self.definition_class)
        tables = {}
        for name in ("mortality", "reinsurance_mortality_credit_life"):
            tables[name] = declare(
                declared,
                name,
                MortalityAssumption,
                "age_sex",
                "fraction" if name == "reinsurance_mortality_credit_life" else "probability",
                columns=SEX,
                format_name="avk_mortality_v1",
            )
        for basis, prefix in (("reserving", "RE"), ("be", "BE")):
            name = f"mortality_loadings_credit_life/{basis}"
            tables[name] = declare(
                declared,
                name,
                MortalityAssumption,
                "age_sex",
                "fraction",
                columns=tuple(f"{prefix}_{key}" for key in ("M_NS", "M_S", "F_NS", "F_S")),
                logical_name="mortality_loadings_credit_life",
                format_name="avk_mortality_v1",
            )
        for name, model in (
            ("lapse_rates_credit_life", LapseAssumption),
            ("commissions_credit_life", CommissionAssumption),
        ):
            tables[name] = declare(declared, name, model, "year_channel", "probability")
        tables["expenses_credit_life"] = declare(
            declared,
            "expenses_credit_life",
            ExpenseAssumption,
            "knots",
            "mixed",
            columns=INITIAL,
            below="clamp",
            above="clamp",
        )
        tables["expenses_credit_life/renewal"] = declare(
            declared,
            "expenses_credit_life/renewal",
            ExpenseAssumption,
            "categories",
            "mixed",
            columns=RENEWAL,
            below="error",
            above="error",
            logical_name="expenses_credit_life",
            format_name="avk_expenses_v1",
        )
        tables["interest_rates"] = declare(
            declared,
            "interest_rates",
            InterestCurveAssumption,
            "annual_curve",
            "annual_effective",
            columns=("ROI", "VROI", "Reference Forward Rates"),
            below="error",
            above="error",
        )
        for name, column in IFRS_SCHEDULES.items():
            tables[name] = declare(
                declared,
                name,
                ExpenseAssumption,
                "annual_schedule",
                "mixed",
                columns=(column,),
                logical_name="ifrs17_renewal_expenses_credit_life",
            )
        tables["ifrs17_interest_rates"] = declare(
            declared,
            "ifrs17_interest_rates",
            InterestCurveAssumption,
            "annual_curve",
            "annual_effective",
            columns=("if17_Current_ROI", "if17_Locked_in_Rate", "if17_Reference Forward Rates"),
            below="error",
            above="error",
        )
        return AssumptionSpec(
            self.code, tables, SCENARIOS if self.measurement else SCENARIOS[:3] + SCENARIOS[4:]
        )

    def model_point_adapter(self, tables: Mapping[str, Table]) -> ModelPointAdapter:
        return CreditLifeModelPointAdapter(tables, CreditLife.FIELDS)

    def validator(self) -> CreditLifePolicyValidator:
        return CreditLifePolicyValidator()

    def output_schema(self, run_type: str) -> OutputSchema:
        return OutputSchema(
            entries=(
                *(
                    (f"decrements_{alias}_reserving", column, "reserving")
                    for alias, column in EXITS
                ),
                *((f"decrements_{alias}_BE", column, "be") for alias, column in EXITS),
                *(
                    (f"cashflows_{alias}_reserving", column, "reserving")
                    for alias, column in CASHFLOWS
                ),
                *(
                    (f"cashflows_{name}_BE", name, "be")
                    for name in (
                        "reins_sum_assured",
                        "reins_premiums",
                        "reins_recoveries",
                    )
                ),
                *((f"cashflows_{name}_BE", column, "be") for name, column in BE_LAYER),
                *((f"MCEV_{name}_BE", column, "be") for name, column in PRESENT_VALUES),
            ),
            keys=(
                ("Policy_Number", POLICY, None),
                ("Policy_Month", "policy_month", None),
                ("Calendar_Month", CALENDAR, None),
                ("Projection_Step", STEP, None),
                ("Modal_Factor", "modal_factor", None),
            ),
            integer_keys=frozenset({"Policy_Month"}),
            seriatim=(
                *(
                    (f"MCEV_{name}_BE", name, "be", 0)
                    for name in ("pvfp", "pv_premium", "bel", "fcc")
                ),
                ("cashflows_gross_reserve_pp_reserving", "gross_reserve_pp", "reserving", 0),
                ("cashflows_net_reserve_pp_reserving", "net_reserve_pp", "reserving", 0),
                ("Annualised_premium", "premiums", "be", 1),
            ),
        )


class IfrsCreditLifeFactory(CreditLifeFactory):
    measurement = True
    definition_class = IfrsCreditLife
