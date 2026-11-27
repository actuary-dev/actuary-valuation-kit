"""Policy errors and warnings, shared by CLI checks and API pre-flight.

Product rules live with their product (`products/<family>/validation.py`).
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
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

    def validate_companions(
        self,
        policies: pl.DataFrame,
        companions: Mapping[str, pl.DataFrame],
        valuation_date: date,
    ) -> list[Issue]:
        """Check the companion rows of `policies` (a whole book or one streamed batch).

        Rows of other policies are out of scope here; `companion_orphans` reports rows
        whose policy is in no batch, once the whole book has been seen."""
        return []

    def companion_orphans(
        self,
        known: Callable[[pl.Series], pl.Series],
        companions: Mapping[str, pl.DataFrame],
    ) -> list[Issue]:
        """Companion rows naming no policy of the book: `known(numbers)` is True where a
        policy number belongs to the run's book (compared as the prepared Policy_Number)."""
        return []
