"""Term model points: vectorized preparation from the run's validated tables."""

from collections.abc import Mapping

import numpy as np
import polars as pl

from avk.inputs.policies import ModelPointAdapter, PreparationConfig, dates, numeric
from avk.model.data import ModelPoints, Table
from avk.products.term.bindings import RENEWAL
from avk.products.term.validation import GENDER_CODES, SMOKING_CODES
from avk.runtime.errors import InputError

# Policy keys that index a table directly: (column, table, table axis, error fragment).
KEYED_LOOKUPS = (
    ("Premium Frequency", "premium_frequency_factors", 0, "premium frequency not in Modal_Factor"),
    ("Distribution Channel", "lapse_rates_term", 1, "channel not in"),
    ("Distribution Channel", "commissions_term", 1, "channel not in"),
)


class TermModelPointAdapter(ModelPointAdapter):
    def __init__(
        self, code: str, table: str, tables: Mapping[str, Table], fields: tuple[str, ...]
    ) -> None:
        self.code = code
        self.table = table
        self.tables = tables
        self.fields = fields

    def product_codes(self, frame: pl.DataFrame) -> pl.Series:
        for name in ("Product_Code", "Product Code"):
            if name in frame.columns:
                return frame[name].cast(pl.String).rename("Product_Code")
        return pl.repeat(self.code, frame.height, dtype=pl.String, eager=True).alias("Product_Code")

    def check_keys(self, frame: pl.DataFrame) -> None:
        """Prove every keyed lookup lands on a table row before any field is derived."""
        for column, name, axis, fragment in KEYED_LOOKUPS:
            keys = self.tables[name].axes[axis].keys
            values = frame[column].cast(pl.Float64, strict=False)
            if values.is_null().any() or (~values.is_in(list(keys))).any():
                raise InputError(f"{fragment} {name}")

    def prepare(self, frame: pl.DataFrame, config: PreparationConfig) -> ModelPoints[pl.DataFrame]:
        self.check_keys(frame)
        codes = self.dispatched_codes(frame, config)
        start = dates("Policy Start Date", frame.schema["Policy Start Date"])
        duration = (
            (config.valuation_date.year - start.dt.year()) * 12
            + config.valuation_date.month
            - start.dt.month()
            + 1
        )
        prepared = frame.with_columns(
            start.alias("Policy Start Date"),
            numeric("Policy Term (Years)").alias("Policy_Term"),
            numeric("Premium Payment Term").cast(pl.Int64).alias("Premium_Payment_Term"),
            numeric("Age at Policy Start").cast(pl.Int64).alias("Age_at_Entry"),
            numeric("Sum Assured").alias("Sum_Assured"),
            numeric("Premium Amount").alias("Premium_Amount"),
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
        additions: list[pl.Series | pl.Expr] = []
        sa = prepared["Sum_Assured"].to_numpy()
        smoker = prepared["Smoking_Status_Code"].to_numpy()
        for name, field in (
            ("mortality_loadings_term", "EMR"),
            ("reinsurance_mortality_loadings_term", "reins_EMR"),
        ):
            values = self.tables[name].values
            # Work over the tiny table categories, never over policy rows.
            result = np.empty(prepared.height, dtype=np.float64)
            for code in np.unique(smoker):
                bands = values[values[:, 2] == code]
                bands = bands[np.argsort(bands[:, 0])]
                mask = smoker == code
                if not len(bands) or (sa[mask] < bands[0, 0]).any():
                    raise InputError(f"Sum Assured is below the first sum-assured band of {name}")
                result[mask] = bands[np.searchsorted(bands[:, 0], sa[mask], side="right") - 1, 3]
            additions.append(pl.Series(field, result))
        for name, prefix in (
            ("expenses_term", "initial"),
            ("ifrs17_initial_expenses_term", "ifrs_initial"),
        ):
            values = self.tables[name].values
            for index, field in ((1, "percent_prem"), (2, "fixed"), (3, "percent_sa")):
                additions.append(
                    pl.Series(
                        f"{prefix}_{field}_expense_rate",
                        np.interp(sa, values[:, 0], values[:, index]),
                    )
                )
        # Renewal expense categories are resolved here, like the initial-expense knots.
        renewal = self.tables["expenses_term/renewal"].values
        for category, field in (
            ("Fixed expenses", "renewal_fixed_expense"),
            ("% of Prem", "renewal_percent_prem_expense_rate"),
            ("Claim expenses", "claim_expense_percent"),
        ):
            value = float(renewal[RENEWAL.index(category)])
            additions.append(pl.lit(value, dtype=pl.Float64).alias(field))
        # Month-zero lookups are evaluated even for future or matured policies.
        minimum_age = prepared["Age_at_Entry"] + (prepared["Duration_in_Months"] - 1) // 12
        for name in ("mortality", "reinsurance_mortality"):
            first = self.tables[name].axes[0].start
            assert first is not None
            if (minimum_age < first).any() or (prepared["Age_at_Entry"] < first).any():
                raise InputError(f"Policy age is below the first age of {name} ({first})")
        return ModelPoints(prepared.with_columns(additions), self.fields)
