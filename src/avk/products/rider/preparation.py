"""Vectorized rider preparation; dates and Rider_Option resolve before the kernel."""

import numpy as np
import polars as pl

from avk.inputs.policies import PreparationConfig, dates, numeric
from avk.model.data import ModelPoints
from avk.products.rider.validation import OPTIONS
from avk.products.term.bindings import RENEWAL
from avk.products.term.preparation import TermModelPointAdapter
from avk.products.term.validation import GENDER_CODES, SMOKING_CODES
from avk.runtime.errors import InputError


class RiderModelPointAdapter(TermModelPointAdapter):
    def product_codes(self, frame: pl.DataFrame) -> pl.Series:
        return frame.select(
            numeric("Rider Option")
            .replace_strict(OPTIONS, return_dtype=pl.String)
            .alias("Product_Code")
        ).to_series()

    def prepare(self, frame: pl.DataFrame, config: PreparationConfig) -> ModelPoints[pl.DataFrame]:
        self.check_keys(frame)
        codes = self.dispatched_codes(frame, config)
        start = dates("Policy Start Date", frame.schema["Policy Start Date"])
        duration = (
            (config.valuation_date.year - start.dt.year()) * 12
            + config.valuation_date.month
            - start.dt.month()
            - (config.valuation_date.day < start.dt.day()).cast(pl.Int64)
            + 1
        )
        prepared = frame.with_columns(
            start.alias("Policy Start Date"),
            numeric("Policy Term (Years)").alias("Policy_Term"),
            numeric("Premium Payment Term").cast(pl.Int64).alias("Premium_Payment_Term"),
            numeric("Age at Policy Start").cast(pl.Int64).alias("Age_at_Entry"),
            numeric("Sum Assured").alias("Sum_Assured"),
            numeric("Rider Premium").alias("Premium_Amount"),
            numeric("Base Premium").alias("Base_Premium"),
            numeric("Rider Option").cast(pl.Int64).alias("Rider_Option"),
            numeric("Premium Frequency").cast(pl.Int64).alias("Premium_Frequency"),
            numeric("Distribution Channel").cast(pl.Int64).alias("Distribution_Channel"),
            pl.col("Gender").replace_strict(GENDER_CODES).cast(pl.Int64).alias("Gender_Code"),
            pl.col("Smoking Status")
            .replace_strict(SMOKING_CODES)
            .cast(pl.Int64)
            .alias("Smoking_Status_Code"),
            duration.cast(pl.Int64).alias("Duration_in_Months"),
            pl.col("Policy Number").alias("Policy_Number"),
            codes,
        )
        if "Policy_Status" not in prepared.columns:
            if "Policy Status" not in prepared.columns:
                raise InputError(f"{self.table}: missing required column 'Policy Status'")
            prepared = prepared.with_columns(pl.col("Policy Status").alias("Policy_Status"))
        if prepared["Policy_Status"].null_count() == prepared.height:
            prepared = prepared.with_columns(pl.lit(float("nan")).alias("Policy_Status"))
        sa = prepared["Sum_Assured"].to_numpy()
        additions: list[pl.Series | pl.Expr] = []
        for name, prefix in (
            ("expenses_rider", "initial"),
            ("ifrs17_initial_expenses_rider", "ifrs_initial"),
        ):
            values = self.tables[name].values
            for index, field in ((1, "percent_prem"), (2, "fixed"), (3, "percent_sa")):
                additions.append(
                    pl.Series(
                        f"{prefix}_{field}_expense_rate",
                        np.interp(sa, values[:, 0], values[:, index]),
                    )
                )
        renewal = self.tables["expenses_rider/renewal"].values
        for category, field in (
            ("Fixed expenses", "renewal_fixed_expense"),
            ("% of Prem", "renewal_percent_prem_expense_rate"),
            ("Claim expenses", "claim_expense_percent"),
        ):
            additions.append(pl.lit(float(renewal[RENEWAL.index(category)])).alias(field))
        minimum_age = prepared["Age_at_Entry"] + (prepared["Duration_in_Months"] - 1) // 12
        first = self.tables["mortality"].axes[0].start
        assert first is not None
        if (minimum_age < first).any() or (prepared["Age_at_Entry"] < first).any():
            raise InputError(f"Policy age is below the first age of mortality ({first})")
        return ModelPoints(prepared.with_columns(additions), self.fields)
