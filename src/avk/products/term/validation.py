"""Term policy validation."""

import polars as pl

from avk.inputs.policies import dates, numeric
from avk.inputs.validation import Issue, MaturityRule, PolicyValidator
from avk.products.term.bindings import SEX

REQUIRED = (
    "Policy Number",
    "Policy Start Date",
    "Policy Term (Years)",
    "Premium Payment Term",
    "Sum Assured",
    "Premium Amount",
    "Premium Frequency",
    "Distribution Channel",
    "Age at Policy Start",
    "Gender",
    "Smoking Status",
)
# Accepted labels and the codes preparation assigns them; validation lists the labels. A sex
# code is the column's position in the mortality tables' declared order (bindings.SEX).
GENDER_CODES = {
    "M": SEX.index("Male"),
    "F": SEX.index("Female"),
    "Male": SEX.index("Male"),
    "Female": SEX.index("Female"),
}
SMOKING_CODES = {"NS": 0, "S": 1, "Non-Smoker": 0, "Smoker": 1}
GENDERS = list(GENDER_CODES)
SMOKING = list(SMOKING_CODES)


class TermPolicyValidator(PolicyValidator):
    maturity_rule = MaturityRule("Policy Start Date", "Policy Term (Years)")

    def __init__(self, code: str) -> None:
        self.prefix = f"[{code}] policy data"

    def validate(self, frame: pl.DataFrame) -> list[Issue]:
        prefix = self.prefix
        if frame.is_empty():
            return [Issue("error", f"{prefix} has no policies")]
        missing = sorted(set(REQUIRED) - set(frame.columns))
        if missing:
            return [Issue("error", f"{prefix}: missing required column(s): {missing}")]
        issues = []
        if frame["Policy Number"].is_duplicated().any():
            issues.append(
                Issue("error", f"{prefix}: duplicate value(s) in identifier column 'Policy Number'")
            )
        if frame["Policy Number"].is_null().any():
            issues.append(Issue("error", f"{prefix}: missing identifier in 'Policy Number'"))
        numeric_columns = (
            "Sum Assured",
            "Premium Amount",
            "Age at Policy Start",
            "Policy Term (Years)",
            "Premium Payment Term",
            "Premium Frequency",
            "Distribution Channel",
        )
        converted = frame.select(numeric(column) for column in numeric_columns)
        for column in numeric_columns:
            series = converted[column]
            if series.is_null().any() or (~series.is_finite()).any():
                issues.append(
                    Issue(
                        "error",
                        f"{prefix}: column '{column}' has non-numeric value(s) "
                        "or non-finite value(s)",
                    )
                )
            elif column in ("Policy Term (Years)", "Premium Payment Term"):
                if (series <= 0).any():
                    issues.append(
                        Issue("error", f"{prefix}: column '{column}' has non-positive value(s)")
                    )
            elif column not in ("Premium Frequency", "Distribution Channel") and (series < 0).any():
                issues.append(Issue("error", f"{prefix}: column '{column}' has negative value(s)"))
        if (
            frame.select(dates("Policy Start Date", frame.schema["Policy Start Date"]))
            .to_series()
            .is_null()
            .any()
        ):
            issues.append(
                Issue(
                    "error", f"{prefix}: date column 'Policy Start Date' has unparseable value(s)"
                )
            )
        for column, allowed in (("Gender", GENDERS), ("Smoking Status", SMOKING)):
            if frame[column].is_null().any() or (~frame[column].is_in(allowed)).any():
                issues.append(
                    Issue("error", f"{prefix}: unrecognised {column} value(s); expected {allowed}")
                )
        if (converted["Premium Amount"] == 0).any():
            issues.append(
                Issue("warning", f"{prefix}: column 'Premium Amount' has row(s) with zero premium")
            )
        return issues
