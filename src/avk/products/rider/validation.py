"""Rider raw-input checks, option agreement and day-adjusted maturity."""

import polars as pl

from avk.inputs.policies import numeric
from avk.inputs.validation import Issue, MaturityRule
from avk.products.term.validation import TermPolicyValidator

OPTIONS = {1: "ACCIDENTAL_DEATH_RIDER", 2: "CRITICAL_ILLNESS_RIDER", 3: "DISABILITY_RIDER"}


class RiderPolicyValidator(TermPolicyValidator):
    maturity_rule = MaturityRule("Policy Start Date", "Policy Term (Years)", adjust_day=True)

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def validate(self, frame: pl.DataFrame) -> list[Issue]:
        missing = {"Rider Premium", "Base Premium", "Rider Option"} - set(frame.columns)
        if missing:
            return [Issue("error", f"{self.prefix}: missing required columns {sorted(missing)}")]
        # Reuse the common numeric/date/category checks on the rider's premium column.
        issues = super().validate(
            frame.with_columns(pl.col("Rider Premium").alias("Premium Amount"))
        )
        if frame.is_empty():
            return issues
        values = frame.select(numeric("Base Premium"), numeric("Rider Option"))
        if (
            values["Base Premium"].is_null().any()
            or not values["Base Premium"].is_finite().all()
            or (values["Base Premium"] < 0).any()
        ):
            issues.append(
                Issue("error", f"{self.prefix}: Base Premium must be finite and nonnegative")
            )
        expected = next(option for option, code in OPTIONS.items() if code == self.code)
        if values["Rider Option"].is_null().any() or (values["Rider Option"] != expected).any():
            issues.append(
                Issue("error", f"{self.prefix}: Rider_Option does not match product {self.code}")
            )
        for name in ("Product_Code", "Product Code"):
            if name not in frame.columns:
                continue
            labels = frame[name].replace(
                {
                    "Accidental Death": "ACCIDENTAL_DEATH_RIDER",
                    "Critical Illness": "CRITICAL_ILLNESS_RIDER",
                    "Disability Rider": "DISABILITY_RIDER",
                }
            )
            if labels.is_null().any() or (labels != self.code).any():
                issues.append(Issue("error", f"{self.prefix}: Rider_Option does not match product"))
        return issues
