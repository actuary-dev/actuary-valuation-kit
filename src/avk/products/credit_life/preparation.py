"""Vectorized preparation of CREDIT_LIFE model points and loan schedules."""

import math
from collections.abc import Callable, Mapping
from functools import lru_cache

import numpy as np
import polars as pl
from numba import config as numba_config
from numba import vectorize
from numpy.typing import NDArray

from avk.inputs.policies import ModelPointAdapter, PreparationConfig, dates, numeric
from avk.inputs.validation import Issue, MaturityRule, PolicyValidator
from avk.model import arithmetic  # noqa: F401 - compile-time math.fma support
from avk.model.data import ModelPoints, Table
from avk.products.term.bindings import RENEWAL
from avk.products.term.validation import GENDER_CODES, SMOKING_CODES
from avk.runtime.errors import InputError

NUMERIC = (
    "Premium",
    "Loan Amount",
    "EMI amount",
    "Interest Rate",
    "Mode",
    "Age at Policy Start",
    "Policy Term (Years)",
    "Moratorium Period (months)",
    "Interest Accrue",
    "Reducing SA",
    "Mortality Table Loading Flag",
    "Distribution Channel",
)
REQUIRED = (*NUMERIC, "Policy ID", "Policy start date", "Gender", "Smoker")


def _loan_step(balance: float, factor: float, payment: float) -> float:
    """Vector ufunc: exactly rounded multiply/subtract in the loan recursion."""
    return math.fma(balance, factor, -payment)


@lru_cache(maxsize=1)
def _loan_ufunc() -> Callable[
    [NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]
]:
    """Construct only when preparing loans; definition listing must not compile."""
    if numba_config.DISABLE_JIT:  # type: ignore[attr-defined]
        # NumPy broadcasts the native C math.fma callable; no policy-row Python loop.
        plain_fma = np.frompyfunc(math.fma, 3, 1)

        def plain(
            balance: NDArray[np.float64],
            factor: NDArray[np.float64],
            payment: NDArray[np.float64],
        ) -> NDArray[np.float64]:
            return np.asarray(plain_fma(balance, factor, -payment), dtype=np.float64)

        return plain
    return vectorize(["float64(float64, float64, float64)"], nopython=True, cache=True)(_loan_step)  # type: ignore[no-untyped-call,no-any-return]


class CreditLifePolicyValidator(PolicyValidator):
    maturity_rule = MaturityRule("Policy start date", "Policy Term (Years)")

    def validate(self, frame: pl.DataFrame) -> list[Issue]:
        if frame.is_empty():
            return [Issue("error", "[CREDIT_LIFE] policy data has no policies")]
        missing = set(REQUIRED) - set(frame.columns)
        if missing:
            return [Issue("error", f"[CREDIT_LIFE] missing required columns {sorted(missing)}")]
        issues = []
        if frame["Policy ID"].is_null().any() or frame["Policy ID"].is_duplicated().any():
            issues.append(Issue("error", "[CREDIT_LIFE] missing or duplicate Policy ID"))
        for column in NUMERIC:
            values = frame.select(numeric(column)).to_series()
            if column in ("Mode", "Interest Accrue", "Mortality Table Loading Flag"):
                # Apply defaults to source nulls only, and reject coercion failures.
                values = frame.select(
                    pl.when(pl.col(column).is_null())
                    .then(1.0 if column == "Mode" else 0.0)
                    .otherwise(numeric(column))
                ).to_series()
            if values.is_null().any() or not values.is_finite().all():
                issues.append(
                    Issue("error", f"[CREDIT_LIFE] {column} must contain finite numeric values")
                )
            elif column == "Mode":
                if (values == 12).any():
                    issues.append(Issue("error", "CREDIT_LIFE Mode 12 is not supported"))
                elif (values != 1).any():
                    issues.append(Issue("error", "[CREDIT_LIFE] Mode must be 1"))
            elif column in (
                "Interest Accrue",
                "Reducing SA",
                "Mortality Table Loading Flag",
            ):
                if (~values.is_in([0.0, 1.0])).any():
                    issues.append(Issue("error", f"[CREDIT_LIFE] {column} must be 0 or 1"))
            elif column in ("Loan Amount", "Policy Term (Years)"):
                if (values <= 0).any():
                    issues.append(Issue("error", f"[CREDIT_LIFE] {column} must be positive"))
            elif (values < 0).any():
                issues.append(Issue("error", f"[CREDIT_LIFE] {column} must be nonnegative"))
        if (
            frame.select(dates("Policy start date", frame.schema["Policy start date"]))
            .to_series()
            .is_null()
            .any()
        ):
            issues.append(Issue("error", "[CREDIT_LIFE] unparseable Policy start date"))
        return issues


class CreditLifeModelPointAdapter(ModelPointAdapter):
    code, table = "CREDIT_LIFE", "policies_credit_life"

    def __init__(self, tables: Mapping[str, Table], fields: tuple[str, ...]) -> None:
        self.tables, self.fields = tables, fields

    def product_codes(self, frame: pl.DataFrame) -> pl.Series:
        for name in ("Product Code", "Product_Code"):
            if name in frame.columns:
                return frame[name].cast(pl.String).alias("Product_Code")
        return pl.repeat(self.code, frame.height, dtype=pl.String, eager=True).alias("Product_Code")

    def prepare(self, frame: pl.DataFrame, config: PreparationConfig) -> ModelPoints[pl.DataFrame]:
        start = dates("Policy start date", frame.schema["Policy start date"])
        duration = (
            (config.valuation_date.year - start.dt.year()) * 12
            + config.valuation_date.month
            - start.dt.month()
            + 1
        )
        prepared = frame.with_columns(
            *(numeric(name).alias(name.replace(" ", "_")) for name in NUMERIC),
            start.alias("Policy_start_date"),
            pl.col("Policy ID").alias("Policy_Number"),
            self.dispatched_codes(frame, config),
            pl.col("Gender")
            .cast(pl.String)
            .replace_strict(GENDER_CODES, default=1)
            .cast(pl.Int64)
            .alias("Gender_Code"),
            pl.col("Smoker")
            .cast(pl.String)
            .replace_strict(SMOKING_CODES, default=0)
            .cast(pl.Int64)
            .alias("Smoking_Status_Code"),
            duration.cast(pl.Int64).alias("Duration_in_Months"),
            numeric("Policy Term (Years)").alias("Policy_Term"),
            numeric("Mortality Table Loading Flag").fill_null(0).alias("Mortality_Flag"),
        ).with_columns(
            pl.col("Age_at_Policy_Start").cast(pl.Int64),
            pl.col("Moratorium_Period_(months)").cast(pl.Int64),
            pl.col("Mode").fill_null(1),
            pl.col("Interest_Accrue").fill_null(0),
            (pl.col("Gender_Code") * 2 + pl.col("Smoking_Status_Code")).alias("Support_Code"),
            (pl.col("Moratorium_Period_(months)").cast(pl.Int64) - pl.col("Duration_in_Months"))
            .clip(lower_bound=0)
            .alias("Moratorium_Period_ind"),
        )
        for name in ("lapse_rates_credit_life", "commissions_credit_life"):
            if (
                ~prepared["Distribution_Channel"].is_in(list(self.tables[name].axes[1].keys))
            ).any():
                raise InputError(f"channel not in {name}")
        age = prepared["Age_at_Policy_Start"] + (prepared["Duration_in_Months"] - 1) // 12
        for name in (
            "mortality",
            "reinsurance_mortality_credit_life",
            "mortality_loadings_credit_life/reserving",
            "mortality_loadings_credit_life/be",
        ):
            first = self.tables[name].axes[0].start
            assert first is not None
            if (age < first).any() or (prepared["Age_at_Policy_Start"] < first).any():
                raise InputError(f"Policy age is below the first age of {name} ({first})")
        months = config.projection_term * 12
        loan = prepared["Loan_Amount"].to_numpy()
        rate = prepared["Interest_Rate"].to_numpy() / 12 * prepared["Interest_Accrue"].to_numpy()
        emi = prepared["EMI_amount"].to_numpy()
        holiday = prepared["Moratorium_Period_(months)"].to_numpy()
        reducing = prepared["Reducing_SA"].to_numpy() == 1
        schedule = np.empty((prepared.height, months), dtype=np.float64)
        schedule[:, 0] = loan
        for month in range(1, months):
            schedule[:, month] = np.where(
                reducing,
                np.maximum(
                    _loan_ufunc()(schedule[:, month - 1], 1 + rate, emi * (month >= holiday)), 0.0
                ),
                loan,
            )
        indices = np.clip(prepared["Duration_in_Months"].to_numpy().astype(np.int64), 0, months - 1)
        outstanding = schedule[np.arange(prepared.height), indices]
        additions: list[pl.Series | pl.Expr] = [
            # Use the validated single-pay Mode as the premium frequency for IFRS validation.
            pl.col("Mode").alias("Premium_Frequency"),
            pl.Series("Loan_Schedule", schedule, dtype=pl.List(pl.Float64)),
            pl.Series("loan_os", outstanding),
        ]
        values = self.tables["expenses_credit_life"].values
        for index, name in ((1, "percent_prem"), (2, "fixed"), (3, "percent_sa")):
            additions.append(
                pl.Series(
                    f"initial_{name}_expense_rate",
                    np.interp(outstanding, values[:, 0], values[:, index]),
                )
            )
        renewal = self.tables["expenses_credit_life/renewal"].values
        for name, field in (
            ("Fixed expenses", "renewal_fixed_expense"),
            ("Claim expenses", "claim_expense_percent"),
        ):
            additions.append(pl.lit(float(renewal[RENEWAL.index(name)])).alias(field))
        commissions = self.tables["commissions_credit_life"]
        channels = prepared["Distribution_Channel"].to_numpy()
        channel_indices = np.searchsorted(np.asarray(commissions.axes[1].keys), channels)
        year = prepared["Duration_in_Months"].to_numpy() // 12 + 1
        year_indices = np.clip(year.astype(np.int64) - 1, 0, commissions.values.shape[0] - 1)
        deduction = (
            prepared["Premium"].to_numpy()
            * commissions.values[year_indices, channel_indices]
            * (prepared["Duration_in_Months"].to_numpy() + 1 == 1)
        )
        additions.append(pl.Series("upr_commission", deduction))
        return ModelPoints(prepared.with_columns(additions), self.fields)
