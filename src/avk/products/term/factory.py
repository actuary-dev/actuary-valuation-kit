"""Term definition-layer factory: loading specification, preparation, validation."""

from collections.abc import Mapping

from avk.assumptions.context import AssumptionSpec, ScenarioVariable, declare
from avk.assumptions.models import (
    CommissionAssumption,
    ExpenseAssumption,
    InterestCurveAssumption,
    LapseAssumption,
    ModalFactorAssumption,
    MortalityAssumption,
    ReinsuranceAssumption,
)
from avk.inputs.policies import ModelPointAdapter
from avk.model.data import Table
from avk.model.manifest import table_bindings
from avk.outputs.schema import CALENDAR, POLICY, STEP, OutputSchema
from avk.products.registry import ProductFactory
from avk.products.term.bindings import IFRS_SCHEDULES, INITIAL, RENEWAL, SEX
from avk.products.term.formulas import IfrsTerm, Term
from avk.products.term.output_columns import (
    BE_LAYER,
    CASHFLOWS,
    EXITS,
    PRESENT_VALUES,
)
from avk.products.term.preparation import TermModelPointAdapter
from avk.products.term.validation import TermPolicyValidator
from avk.runtime.errors import ConfigError

# Output layer suffixes are shared across all product families.
LAYERS = {"reserving": "reserving", "be": "BE"}
SCENARIOS = (
    ScenarioVariable("roi", "interest_rates", "ROI", "lag", months=1),
    ScenarioVariable("vroi", "interest_rates", "VROI", "lag", months=1),
    ScenarioVariable(
        "reference_forward", "interest_rates", "Reference Forward Rates", "lag", months=1
    ),
    ScenarioVariable(
        "ifrs_current",
        "ifrs17_interest_rates",
        "if17_Current_ROI",
        "fiscal_lag",
        months=13,
        fiscal_start_month="fiscal_start_month",
    ),
    ScenarioVariable(
        "ifrs_locked_in",
        "ifrs17_interest_rates",
        "if17_Locked_in_Rate",
        "fiscal_lead",
        fiscal_start_month="fiscal_start_month",
    ),
    # Unshifted: policy start offsets are applied by the later kernel.
    ScenarioVariable(
        "ifrs_reference_forward", "ifrs17_interest_rates", "if17_Reference Forward Rates", "lag"
    ),
)


class TermFactory(ProductFactory):
    code = "TERM"
    policy_table = "policies_term"
    definition_class = Term
    parameter_column = "TERM"

    def definition(self, extensions: tuple[str, ...] = ()) -> type[Term]:
        if extensions:
            raise ConfigError(f"Term extensions are not implemented: {extensions}")
        return self.definition_class

    def assumption_spec(self) -> AssumptionSpec:
        declared = table_bindings(self.definition_class)
        tables = {}
        for name in ("mortality", "reinsurance_mortality"):
            tables[name] = declare(
                declared, name, MortalityAssumption, "age_sex", "probability", columns=SEX
            )
        for name, model in (
            ("lapse_rates_term", LapseAssumption),
            ("commissions_term", CommissionAssumption),
        ):
            tables[name] = declare(declared, name, model, "year_channel", "probability")
        for name in ("mortality_loadings_term", "reinsurance_mortality_loadings_term"):
            tables[name] = declare(
                declared,
                name,
                ReinsuranceAssumption,
                "smoker_sa_bands",
                "mixed",
                columns=("Band_Lower Limit", "Band_Upper Limit", "Is_Smoker", "Value"),
                below="error",
                above="clamp",
            )
        for name in ("expenses_term", "ifrs17_initial_expenses_term"):
            # Sum-assured knots: interpolation clamps at both ends.
            tables[name] = declare(
                declared,
                name,
                ExpenseAssumption,
                "knots",
                "mixed",
                columns=INITIAL,
                below="clamp",
                above="clamp",
            )
        tables["expenses_term/renewal"] = declare(
            declared,
            "expenses_term/renewal",
            ExpenseAssumption,
            "categories",
            "mixed",
            columns=RENEWAL,
            below="error",
            above="error",
            logical_name="expenses_term",
            format_name="avk_expenses_v1",
        )
        # The IFRS 17 renewal schedules: one value column of the annual table each, read by
        # formulas as monthly curves (`IfrsBestEstimate`).
        for name, column in IFRS_SCHEDULES.items():
            tables[name] = declare(
                declared,
                name,
                ExpenseAssumption,
                "annual_schedule",
                "mixed",
                columns=(column,),
                logical_name="ifrs17_renewal_expenses_term",
            )
        for name, columns in (
            ("interest_rates", ("ROI", "VROI", "Reference Forward Rates")),
            (
                "ifrs17_interest_rates",
                ("if17_Current_ROI", "if17_Locked_in_Rate", "if17_Reference Forward Rates"),
            ),
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
        tables["premium_frequency_factors"] = declare(
            declared,
            "premium_frequency_factors",
            ModalFactorAssumption,
            "frequency",
            "fraction",
            columns=(self.parameter_column,),
            below="error",
            above="error",
        )
        return AssumptionSpec(self.code, tables, SCENARIOS, parameter_column=self.parameter_column)

    def model_point_adapter(self, tables: Mapping[str, Table]) -> ModelPointAdapter:
        return TermModelPointAdapter(
            self.code, self.policy_table, tables, self.definition_class.FIELDS
        )

    def output_schema(self, run_type: str) -> OutputSchema:
        """Term output columns in file order.

        The reserving layer (decrements, gross cashflows, reinsurance, net reserve), the BE
        decrements, the BE layer (cashflows, profit chain, solvency capital), the BE
        reinsurance and the present values, the IFRS BEL group (`MCEV_ifrs_*`) last. The
        seriatim file holds four present
        values and both reserves at step 0 and the annualised premium at step 1.
        """
        res, be = LAYERS["reserving"], LAYERS["be"]
        reserving = tuple(
            (f"decrements_{dumped}_{res}", column, "reserving") for dumped, column in EXITS
        ) + tuple((f"cashflows_{name}_{res}", name, "reserving") for name in CASHFLOWS)
        best_estimate = (
            tuple((f"decrements_{dumped}_{be}", column, "be") for dumped, column in EXITS)
            + tuple((f"cashflows_{name}_{be}", column, "be") for name, column in BE_LAYER)
            + tuple((f"cashflows_{name}_{be}", name, "be") for name in CASHFLOWS[11:15])
            + tuple((f"MCEV_{name}_{be}", column, "be") for name, column in PRESENT_VALUES)
        )
        seriatim = (
            *(
                (f"MCEV_{name}_{be}", name, "be", 0)
                for name in ("pvfp", "pv_premium", "bel", "fcc")
            ),
            *(
                (f"cashflows_{name}_{res}", name, "reserving", 0)
                for name in ("gross_reserve_pp", "net_reserve_pp")
            ),
            ("Annualised_premium", "annualised_premium", None, 1),
        )
        return OutputSchema(
            entries=reserving + best_estimate,
            keys=(
                ("Policy_Number", POLICY, None),
                ("Policy_Month", "policy_month", None),
                ("Calendar_Month", CALENDAR, None),
                ("Projection_Step", STEP, None),
                ("Modal_Factor", "modal_factor", None),
            ),
            integer_keys=frozenset({"Policy_Month"}),
            seriatim=seriatim,
        )

    def validator(self) -> TermPolicyValidator:
        return TermPolicyValidator(self.code)


class IfrsTermFactory(TermFactory):
    definition_class = IfrsTerm
