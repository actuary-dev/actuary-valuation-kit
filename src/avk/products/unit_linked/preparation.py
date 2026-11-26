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
    VARIANTS_TABLE,
)
from avk.products.unit_linked.formulas import FIELDS, REGIME_FIELDS, SLOT_FIELDS, VARIANT_FEATURES
from avk.products.unit_linked.validation import (
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
INTEGER_SLOT_FIELDS = ("Present", "Fund_Index")
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
            "unit_price",
            pl.col("fmc").alias("FMC"),
            pl.col("alpha").alias("Alpha"),
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
                (numeric("Units") * pl.col("unit_price")).alias("Value"),
                numeric("Premiums Allocated To Fund").alias("Premiums_Allocated"),
                numeric("Guaranteed Unit Price").alias("Guaranteed_Price"),
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
