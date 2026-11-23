"""Policy errors and warnings, shared by CLI checks and API pre-flight.

Product rules live with their product (`products/<family>/validation.py`).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Literal

import polars as pl

from avk.inputs.policies import dates, numeric


@dataclass(frozen=True)
class Issue:
    severity: Literal["error", "warning"]
    message: str


@dataclass(frozen=True)
class MaturityRule:
    """Raw columns and the family's retained inclusive policy-month convention."""

    start_column: str
    term_column: str
    adjust_day: bool = False

    def expired(self, frame: pl.DataFrame, valuation_date: date) -> pl.Expr:
        start = dates(self.start_column, frame.schema[self.start_column])
        duration = (
            (valuation_date.year - start.dt.year()) * 12
            + valuation_date.month
            - start.dt.month()
            + 1
        )
        if self.adjust_day:
            duration = duration - (valuation_date.day < start.dt.day()).cast(pl.Int64)
        return duration > numeric(self.term_column) * 12


class PolicyValidator(ABC):
    """Checks raw policy rows before preparation; never raises for a data problem."""

    @property
    @abstractmethod
    def maturity_rule(self) -> MaturityRule:
        """Every product declares its maturity columns and retained duration convention."""

    @abstractmethod
    def validate(self, frame: pl.DataFrame) -> list[Issue]: ...

    def validate_at(self, frame: pl.DataFrame, valuation_date: date) -> list[Issue]:
        issues = self.validate(frame)
        if not any(issue.severity == "error" for issue in issues):
            expired = frame.filter(self.maturity_rule.expired(frame, valuation_date))
            if expired.height:
                issues.append(
                    Issue(
                        "error", f"{expired.height} policy row(s) matured before the valuation date"
                    )
                )
        return issues
