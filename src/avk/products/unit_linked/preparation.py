"""Unit-linked model points: policy fields, variant and regime features, the DPF holding
and the fund holdings pivoted into `MAX_FUND_SLOTS` slots, all vectorised over rows."""

from collections.abc import Mapping

import polars as pl

from avk.inputs.policies import ModelPointAdapter, PreparationConfig, dates, numeric
from avk.model.data import ModelPoints, Table
from avk.products.unit_linked.bindings import (
    ASSET_CLASSES,
    CAPS_TABLE,
    FUNDS_TABLE,
    GENDER_CODES,
    HOLDINGS_TABLE,
    MAX_FUND_SLOTS,
    SMOKER_CODES,
    STRATEGY_COLUMN,
    TOPUP_POLICY_FIELDS,
    TOPUP_UNITS,
    VARIANTS_TABLE,
)
from avk.products.unit_linked.formulas import FIELDS, REGIME_FIELDS, SLOT_FIELDS, VARIANT_FEATURES
from avk.products.unit_linked.strategies import prepare_strategies, strategy_policy_messages
from avk.products.unit_linked.validation import (
    ALLOCATION_TOLERANCE,
    check_policies_against_tables,
    check_tables,
    keyed_frames,
    months_elapsed,
)
from avk.runtime.errors import ConfigError, InputError

# Prepared policy fields from raw columns: (field, column, integer).
POLICY_FIELDS = (
    ("Policy_Term", "Policy Term (Years)", True),
    ("Premium_Payment_Term", "Premium Payment Term (Years)", True),
    ("Premium_Frequency", "Premium Frequency", True),
    ("Annualised_Premium", "Annualised Premium", False),
    ("Sum_Assured", "Sum Assured", False),
    ("Distribution_Channel", "Distribution Channel", True),
    ("Age_at_Entry", "Age at Policy Start", True),
    ("EMR", "EMR", False),
    ("Flat_Extra", "Flat Extra", False),
    ("Paid_Up_Sum_Assured", "Paid Up Sum Assured", False),
    ("Premiums_Paid_To_Date", "Premiums Paid To Date", False),
    ("Instalments_Paid", "Instalments Paid", True),
    ("PAC_To_Date", "Premium Allocation Charges To Date", False),
    ("Admin_To_Date", "Policy Administration Charges To Date", False),
    ("MC_To_Date", "Mortality Charges To Date", False),
    ("GC_To_Date", "Guarantee Charges To Date", False),
    ("Loyalty_To_Date", "Loyalty Additions To Date", False),
    ("PW_To_Date", "Partial Withdrawals To Date", False),
    ("PW_Current_Year", "Withdrawals Current Policy Year", False),
    ("PW_Previous_Year", "Withdrawals Previous Policy Year", False),
    ("FV_Sum_Current_Year", "Fund Value Sum Current Policy Year", False),
    ("Disc_Charge_Paid", "Discontinuance Charge Paid", False),
)
WEIGHTS = tuple(f"W_{a}" for a in ASSET_CLASSES)
PREPARED_FIELDS = FIELDS  # the model-point contract, spelled in formulas.py
INTEGER_SLOT_FIELDS = ("Present", "Fund_Index", "Selectable", "Guarantee_Type")
KEY = "_policy_key"
RUN_TYPES = ("Valuation",)


def require_valuation(run_type: str) -> None:
    if run_type not in RUN_TYPES:
        raise ConfigError("UNIT_LINKED supports the Valuation run type only")


class UnitLinkedModelPointAdapter(ModelPointAdapter):
    """Built per run from the validated tables and the holdings companion table; without
    holdings it serves `product_codes` only."""

    def __init__(
        self,
        code: str,
        table: str,
        tables: Mapping[str, Table],
        fields: tuple[str, ...],
        holdings: pl.DataFrame | None = None,
    ) -> None:
        self.code = code
        self.table = table
        self.tables = tables
        self.fields = fields
        self.holdings = holdings
        self._tables_checked = False

    def product_codes(self, frame: pl.DataFrame) -> pl.Series:
        for name in ("Product_Code", "Product Code"):
            if name in frame.columns:
                return frame[name].cast(pl.String).rename("Product_Code")
        return pl.repeat(self.code, frame.height, dtype=pl.String, eager=True).alias("Product_Code")

    def _check_tables(self) -> None:
        if not self._tables_checked:
            messages = check_tables(self.tables)
            if messages:
                raise InputError("\n".join(messages))
            self._tables_checked = True

    def prepare(self, frame: pl.DataFrame, config: PreparationConfig) -> ModelPoints[pl.DataFrame]:
        if self.holdings is None:
            raise ConfigError(f"{self.code}: preparation needs the {HOLDINGS_TABLE} table")
        require_valuation(config.run_type)
        codes = self.dispatched_codes(frame, config)
        self._check_tables()
        frame = frame.with_columns(pl.col("Policy Number").cast(pl.String).alias(KEY))
        holdings = self.holdings.with_columns(
            pl.col("Policy Number").cast(pl.String).alias(KEY)
        ).filter(pl.col(KEY).is_in(frame[KEY].implode()))
        messages = check_policies_against_tables(frame, holdings, self.tables)
        if messages:
            raise InputError("\n".join(messages))
        keyed = keyed_frames(self.tables)
        funds = (
            keyed[FUNDS_TABLE]
            .with_row_index("Fund_Index")
            .with_columns(pl.col("Fund_Index").cast(pl.Int64))
        )
        prepared = self._policy_fields(frame, codes, keyed, config)
        prepared = self._dpf_fields(prepared, holdings, funds)
        prepared = self._slot_fields(prepared, holdings, funds)
        prepared = prepare_strategies(prepared, self.tables)
        messages = (
            topup_messages(prepared, frame, holdings)
            + strategy_policy_messages(prepared)
            + highest_nav_messages(prepared)
        )
        if messages:
            raise InputError("\n".join(messages))
        return ModelPoints(prepared.drop(KEY), self.fields)

    def _policy_fields(
        self,
        frame: pl.DataFrame,
        codes: pl.Series,
        keyed: dict[str, pl.DataFrame],
        config: PreparationConfig,
    ) -> pl.DataFrame:
        start = dates("Policy Start Date", frame.schema["Policy Start Date"])
        frequency = numeric("Premium Frequency")
        single = frequency == 0
        prepared = frame.with_columns(
            *(
                (numeric(column).cast(pl.Int64) if integer else numeric(column)).alias(name)
                for name, column, integer in POLICY_FIELDS
            ),
            *(
                (numeric(column) if column in frame.columns else pl.lit(0.0))
                .cast(pl.Int64 if integer else pl.Float64)
                .alias(name)
                for name, column, integer in TOPUP_POLICY_FIELDS
            ),
            (numeric(STRATEGY_COLUMN) if STRATEGY_COLUMN in frame.columns else pl.lit(0))
            .cast(pl.Int64)
            .alias("Strategy_Id"),
            pl.col("Policy Number").alias("Policy_Number"),
            codes,
            months_elapsed(start, config.valuation_date).alias("Duration_in_Months"),
            pl.col("Gender")
            .cast(pl.String)
            .replace_strict(GENDER_CODES)
            .cast(pl.Int64)
            .alias("Gender_Code"),
            pl.col("Smoking Status")
            .cast(pl.String)
            .replace_strict(SMOKER_CODES)
            .cast(pl.Int64)
            .alias("Smoker_Code"),
            numeric("Policy Status").alias("Policy_Status"),
            (numeric("Flat Extra Term (Years)") * 12)
            .cast(pl.Int64)
            .alias("Flat_Extra_Term_Months"),
            pl.when(single)
            .then(numeric("Annualised Premium"))
            .otherwise(numeric("Annualised Premium") / frequency)
            .alias("Instalment_Premium"),
            pl.when(single)
            .then(pl.lit(1, dtype=pl.Int64))
            .otherwise((frequency * numeric("Premium Payment Term (Years)")).cast(pl.Int64))
            .alias("Instalments_Payable"),
            pl.col("Product Variant").cast(pl.String).alias("_variant"),
        ).with_columns((2 * pl.col("Gender_Code") + pl.col("Smoker_Code")).alias("Charge_Column"))
        variants = keyed[VARIANTS_TABLE].select(
            pl.col("key").alias("_variant"),
            pl.col("variant_id").cast(pl.Int64).alias("Variant_Id"),
            pl.col("regime_id").cast(pl.Int64).alias("Regime_Id"),
            *(pl.col(name).alias(f"V_{name}") for name in VARIANT_FEATURES),
        )
        regimes = keyed[CAPS_TABLE].select(
            pl.col("regime_id").cast(pl.Int64).alias("Regime_Id"),
            *(pl.col(name).alias(f"R_{name}") for name in REGIME_FIELDS),
        )
        return (
            prepared.join(variants, on="_variant", how="left", maintain_order="left")
            .join(regimes, on="Regime_Id", how="left", maintain_order="left")
            .drop("_variant")
        )

    def _dpf_fields(
        self, prepared: pl.DataFrame, holdings: pl.DataFrame, funds: pl.DataFrame
    ) -> pl.DataFrame:
        dpf = funds.filter(pl.col("is_dpf") == 1).row(0, named=True)
        values = (
            holdings.filter(pl.col("Fund Code").cast(pl.String) == dpf["key"])
            .group_by(KEY)
            .agg((numeric("Units").sum() * dpf["unit_price"]).alias("DPF_Value"))
        )
        return prepared.join(values, on=KEY, how="left", maintain_order="left").with_columns(
            pl.col("DPF_Value").fill_null(0.0),  # policies without a DPF holding hold none
            pl.lit(dpf["fmc"], dtype=pl.Float64).alias("DPF_FMC"),
            pl.lit(dpf["alpha"], dtype=pl.Float64).alias("DPF_Alpha"),
            *(pl.lit(dpf[f"w_{a}"], dtype=pl.Float64).alias(f"DPF_W_{a}") for a in ASSET_CLASSES),
        )

    def _slot_fields(
        self, prepared: pl.DataFrame, holdings: pl.DataFrame, funds: pl.DataFrame
    ) -> pl.DataFrame:
        attributes = funds.filter(pl.col("is_dpf") == 0).select(
            pl.col("key").alias("Fund Code"),
            "Fund_Index",
            pl.col("unit_price").alias("Unit_Price"),
            pl.col("guarantee_type").alias("Guarantee_Type"),
            pl.col("fmc").alias("FMC"),
            pl.col("alpha").alias("Alpha"),
            pl.col("selectable").alias("Selectable"),
            *(pl.col(f"w_{a}").alias(f"W_{a}") for a in ASSET_CLASSES),
        )
        held = (
            holdings.with_columns(pl.col("Fund Code").cast(pl.String))
            .join(attributes, on="Fund Code", how="inner")
            .sort(KEY, "Fund_Index")
            .with_columns(
                (pl.col(KEY).cum_count().over(KEY)).alias("_slot"),
                pl.lit(1, dtype=pl.Int64).alias("Present"),
                numeric("Premium Allocation").alias("Allocation"),
                (numeric("Units") * pl.col("Unit_Price")).alias("Value"),
                numeric("Premiums Allocated To Fund").alias("Premiums_Allocated"),
                numeric("Guaranteed Unit Price").alias("Guaranteed_Price"),
                (
                    numeric(TOPUP_UNITS) * pl.col("Unit_Price")
                    if TOPUP_UNITS in holdings.columns
                    else pl.lit(0.0)
                ).alias("Topup_Value"),
            )
        )
        for k in range(1, MAX_FUND_SLOTS + 1):  # over slots, never policies
            slot = held.filter(pl.col("_slot") == k).select(
                KEY, *(pl.col(name).alias(f"Fund_{k}_{name}") for name in SLOT_FIELDS)
            )
            prepared = prepared.join(slot, on=KEY, how="left", maintain_order="left").with_columns(
                pl.col(f"Fund_{k}_Fund_Index").fill_null(-1),
                *(
                    pl.col(f"Fund_{k}_{name}").fill_null(0)  # an empty slot holds zeros
                    for name in SLOT_FIELDS
                    if name != "Fund_Index"
                ),
            )
        return prepared.with_columns(
            pl.col(f"Fund_{k}_{name}").cast(pl.Int64 if name in INTEGER_SLOT_FIELDS else pl.Float64)
            for k in range(1, MAX_FUND_SLOTS + 1)
            for name in SLOT_FIELDS
        )


def topup_messages(
    prepared: pl.DataFrame, policies: pl.DataFrame, holdings: pl.DataFrame
) -> list[str]:
    enabled = prepared.filter(pl.col("V_topup_on") == 1)
    columns = [column for _, column, _ in TOPUP_POLICY_FIELDS if column not in policies.columns]
    if enabled.height and (columns or TOPUP_UNITS not in holdings.columns):
        return [
            f"UNIT_LINKED: topup_on requires policy columns "
            f"{[column for _, column, _ in TOPUP_POLICY_FIELDS]} and holding column {TOPUP_UNITS}"
        ]
    topup_value = pl.sum_horizontal(f"Fund_{k}_Topup_Value" for k in range(1, MAX_FUND_SLOTS + 1))
    if prepared.filter(
        (pl.col("V_topup_on") == 0)
        & pl.any_horizontal(
            *(pl.col(name) != 0 for name, _, _ in TOPUP_POLICY_FIELDS), topup_value != 0
        )
    ).height:
        return ["UNIT_LINKED: nonzero top-up inputs require topup_on"]
    if enabled.is_empty():
        return []
    messages = []
    single = pl.col("Single_Top_Up_Premium") > 0
    month = pl.col("Single_Top_Up_Policy_Month")
    duration = pl.col("Duration_in_Months")
    term = pl.col("Policy_Term") * 12
    ppt = pl.col("Premium_Payment_Term") * 12
    interval = 12 // pl.col("Premium_Frequency").clip(lower_bound=1)
    next_due = duration + 1 + (-duration % interval)
    regular = pl.col("Regular_Top_Up_Premium") > 0
    paid = pl.col("Top_Up_Premiums_Paid_To_Date")
    last = pl.col("Last_Top_Up_Policy_Month")
    allocation = pl.sum_horizontal(f"Fund_{k}_Allocation" for k in range(1, MAX_FUND_SLOTS + 1))
    checks = (
        (
            (single != (month > 0)) | (single & ((month <= duration) | (month > term))),
            "a positive Single Top-Up Premium needs a future "
            "Single Top-Up Policy Month within term",
        ),
        (
            regular & ((pl.col("Premium_Frequency") == 0) | (next_due > ppt)),
            "Regular Top-Up Premium requires a future regular premium due month",
        ),
        (
            (single | regular) & (pl.col("Policy_Status") != 0),
            "future top-ups require active Policy Status 0",
        ),
        (
            (paid > pl.col("Premiums_Paid_To_Date"))
            | ((paid > 0) != (last > 0))
            | (last > duration)
            | ((topup_value > 0) & (paid == 0)),
            "inconsistent top-up premium or unit history and Last Top-Up Policy Month",
        ),
        (
            (single | regular) & ((allocation - 1).abs() > ALLOCATION_TOLERANCE),
            "allocations of a policy with future top-ups must sum to 1",
        ),
        (
            (single | regular | (paid > 0)) & (pl.col("V_topup_sa_multiple") <= 0),
            "top-up premiums require positive topup_sa_multiple",
        ),
    )
    for condition, message in checks:
        if enabled.filter(condition).height:
            messages.append(f"UNIT_LINKED: {message}")
    return messages


def highest_nav_messages(prepared: pl.DataFrame) -> list[str]:
    start = pl.col("V_highest_nav_start_month")
    enabled = prepared.filter(start > 0)
    if enabled.is_empty():
        return []
    during = pl.col("Duration_in_Months") >= start
    guaranteed = []
    bad_seed = []
    for k in range(1, MAX_FUND_SLOTS + 1):
        slot = pl.col(f"Fund_{k}_Guarantee_Type") == 1
        guaranteed.append(slot)
        seed = pl.col(f"Fund_{k}_Guaranteed_Price")
        nav = pl.col(f"Fund_{k}_Unit_Price")
        bad_seed.append(slot & ((during & (seed < nav)) | (~during & (seed != 0))))
    messages = []
    if enabled.filter(pl.any_horizontal(guaranteed) & (start > pl.col("Policy_Term") * 12)).height:
        messages.append("UNIT_LINKED: highest_nav_start_month cannot follow maturity")
    if enabled.filter(pl.any_horizontal(bad_seed)).height:
        messages.append(
            f"{HOLDINGS_TABLE}: Guaranteed Unit Price must be at least current NAV inside "
            "the highest-NAV window and zero before it"
        )
    return messages
