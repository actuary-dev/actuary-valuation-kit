"""Stateless rider factories, strict assumptions and rider output schemas."""

from collections.abc import Mapping

from avk.assumptions.context import AssumptionSpec, declare
from avk.assumptions.models import (
    CommissionAssumption,
    ExpenseAssumption,
    InterestCurveAssumption,
    LapseAssumption,
    ModalFactorAssumption,
    MorbidityAssumption,
    MortalityAssumption,
)
from avk.inputs.policies import ModelPointAdapter
from avk.model.data import Table
from avk.model.lang import Product
from avk.model.manifest import table_bindings
from avk.outputs.schema import CALENDAR, POLICY, STEP, OutputSchema
from avk.products.registry import ProductFactory
from avk.products.rider.accidental_death import AccidentalDeath
from avk.products.rider.critical_illness import CriticalIllness, IfrsCriticalIllness
from avk.products.rider.disability import Disability, IfrsDisability
from avk.products.rider.formulas import IfrsAccidentalDeath
from avk.products.rider.output_columns import BE_LAYER, CI_BE_LAYER
from avk.products.rider.preparation import RiderModelPointAdapter
from avk.products.rider.validation import RiderPolicyValidator
from avk.products.term.bindings import IFRS_SCHEDULES, INITIAL, RENEWAL, SEX
from avk.products.term.factory import SCENARIOS
from avk.runtime.errors import ConfigError

EXITS = (
    ("lives_so_begin", "lives_begin"),
    ("deaths", "deaths"),
    ("adb", "rider_event"),
    ("lapses", "lapses"),
    ("maturities", "maturities"),
    ("lives_so_end", "lives_end"),
)
CASHFLOWS = (
    ("premiums", "premiums"),
    ("commissions", "commissions"),
    ("initial_expense", "initial_expense"),
    ("renewal_expenses", "renewal_expenses"),
    ("claim_expenses", "claim_expenses"),
    ("surrender_benefits", "surrender_benefits"),
    ("interest_on_cashflows", "interest_on_cashflows"),
    ("net_cashflows", "net_cashflows"),
    ("adb_benefit", "adb_benefit"),
)
RESERVES = (
    ("discounted_cf_reserving", "discounted_net_cf"),
    ("gross_reserve_pp", "gross_reserve_pp"),
    ("upr", "upr"),
)
REINSURANCE = tuple(
    (name, name)
    for name in (
        "reins_sum_assured",
        "reins_premiums",
        "reins_recoveries",
        "net_cf_with_reinsurance",
    )
)
NET_RESERVES = tuple((name, name) for name in ("discounted_cf_with_reins", "net_reserve_pp"))


class RiderFactory(ProductFactory):
    """Base factory; subclasses declare their definition, option and morbidity columns."""

    definition_class: type[Product]
    morbidity_columns: tuple[str, ...]
    exits: tuple[tuple[str, str], ...] = EXITS
    cashflows: tuple[tuple[str, str], ...] = CASHFLOWS
    be_layer: tuple[tuple[str, str], ...] = BE_LAYER
    measurement = False

    def definition(self, extensions: tuple[str, ...] = ()) -> type[Product]:
        if extensions:
            raise ConfigError(f"{self.code}: extensions are not implemented: {extensions}")
        return self.definition_class

    def assumption_spec(self) -> AssumptionSpec:
        declared = table_bindings(self.definition_class)
        tables = {
            "mortality": declare(
                declared,
                "mortality",
                MortalityAssumption,
                "age_sex",
                "probability",
                columns=SEX,
            )
        }
        for name in ("morbidity", "reinsurance_morbidity"):
            tables[name] = declare(
                declared,
                name,
                MorbidityAssumption,
                "age_sex",
                "probability",
                columns=self.morbidity_columns,
                format_name="avk_morbidity_v1",
            )
        for name, model in (
            ("lapse_rates_term", LapseAssumption),
            ("commissions_term", CommissionAssumption),
        ):
            tables[name] = declare(declared, name, model, "year_channel", "probability")
        for name in ("expenses_rider", "ifrs17_initial_expenses_rider"):
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
        tables["expenses_rider/renewal"] = declare(
            declared,
            "expenses_rider/renewal",
            ExpenseAssumption,
            "categories",
            "mixed",
            columns=RENEWAL,
            below="error",
            above="error",
            logical_name="expenses_rider",
            format_name="avk_expenses_v1",
        )
        for name, column in IFRS_SCHEDULES.items():
            tables[name] = declare(
                declared,
                name,
                ExpenseAssumption,
                "annual_schedule",
                "mixed",
                columns=(column,),
                logical_name="ifrs17_renewal_expenses_rider",
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
            columns=(self.code,),
            below="error",
            above="error",
        )
        # Rider does not bind the unused IFRS current curve; retain only reached scenario names.
        return AssumptionSpec(
            self.code,
            tables,
            tuple(s for s in SCENARIOS if self.measurement or s.name != "ifrs_current"),
        )

    def model_point_adapter(self, tables: Mapping[str, Table]) -> ModelPointAdapter:
        return RiderModelPointAdapter(
            self.code, self.policy_table, tables, self.definition_class.FIELDS
        )

    def validator(self) -> RiderPolicyValidator:
        return RiderPolicyValidator(self.code)

    def output_schema(self, run_type: str) -> OutputSchema:
        from avk.products.rider.output_columns import PRESENT_VALUES

        reserving = tuple(
            (f"decrements_{name}_reserving", col, "reserving") for name, col in self.exits
        )
        reserving += tuple(
            (f"cashflows_{name}_reserving", col, "reserving")
            for name, col in (*self.cashflows, *RESERVES, *REINSURANCE, *NET_RESERVES)
        )
        be = tuple((f"cashflows_{name}_BE", col, "be") for name, col in self.be_layer)
        pv = tuple((f"MCEV_{name}_BE", col, "be") for name, col in PRESENT_VALUES)
        reinsurance = tuple((f"cashflows_{name}_BE", col, "be") for name, col in REINSURANCE)
        exits = tuple((f"decrements_{name}_BE", col, "be") for name, col in self.exits)
        return OutputSchema(
            entries=(*reserving, *be, *pv, *reinsurance, *exits),
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
                *(
                    (f"cashflows_{name}_reserving", name, "reserving", 0)
                    for name in ("gross_reserve_pp", "net_reserve_pp")
                ),
                ("Annualised_premium", "annualised_premium", None, 1),
            ),
        )


class AccidentalDeathFactory(RiderFactory):
    code, policy_table = "ACCIDENTAL_DEATH_RIDER", "policies_accidental_death"
    definition_class = AccidentalDeath
    morbidity_columns = ("Accidental Death - Male", "Accidental Death - Female")


class CriticalIllnessFactory(RiderFactory):
    """CI assumptions and schema selected before compilation; no runtime option branch."""

    code, policy_table = "CRITICAL_ILLNESS_RIDER", "policies_critical_illness"
    definition_class = CriticalIllness
    morbidity_columns = ("Critical illness - Male", "Critical illness - Female")
    exits = tuple(
        ("critical_illness", col) if name == "adb" else (name, col) for name, col in EXITS
    ) + (
        ("cumulative_critical_illness", "cumulative_claims"),
        ("deaths_out_of_critical_illness", "stock_deaths"),
        ("net_cumulative_critical_illness", "claim_stock"),
    )
    cashflows = tuple((name, col) for name, col in CASHFLOWS if name != "adb_benefit") + (
        ("ci_benefit", "event_benefit"),
        ("wop_benefit", "wop_benefit"),
    )
    be_layer = CI_BE_LAYER


class DisabilityFactory(RiderFactory):
    """Standalone disability rider with claimant stock and premium waiver."""

    code, policy_table = "DISABILITY_RIDER", "policies_disability"
    definition_class = Disability
    morbidity_columns = ("Disability Rider - Male", "Disability Rider - Female")
    exits = tuple(
        (name.replace("critical_illness", "disability"), col)
        for name, col in CriticalIllnessFactory.exits
    )
    cashflows = tuple(
        (name.replace("ci_benefit", "tpd_benefit"), col)
        for name, col in CriticalIllnessFactory.cashflows
    )
    be_layer = tuple((name.replace("ci_benefit", "tpd_benefit"), col) for name, col in CI_BE_LAYER)


class IfrsAccidentalDeathFactory(AccidentalDeathFactory):
    measurement = True
    definition_class = IfrsAccidentalDeath


class IfrsCriticalIllnessFactory(CriticalIllnessFactory):
    measurement = True
    definition_class = IfrsCriticalIllness


class IfrsDisabilityFactory(DisabilityFactory):
    measurement = True
    definition_class = IfrsDisability
