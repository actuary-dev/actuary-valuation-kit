"""Versioned applicability seam; no jurisdiction catalogue or eligibility classifier."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Applicability:
    method: str
    required_data: tuple[str, ...]
    unsupported: tuple[str, ...]

    @property
    def supported(self) -> bool:
        return not self.unsupported


class Regime(ABC):
    version = "1"

    @abstractmethod
    def applicability(self, capabilities: frozenset[str]) -> Applicability: ...


class GeneralMeasurementModel(Regime):
    def applicability(self, capabilities: frozenset[str]) -> Applicability:
        ports = frozenset(
            {
                "premium_income",
                "benefit_outgo",
                "expense_outgo",
                "acquisition_cost",
                "coverage_units",
            }
        )
        return Applicability(
            "IFRS17 GMM", ("group keys", "locked-in curves"), tuple(sorted(ports - capabilities))
        )
