"""Frozen assumption kinds with required rules and vectorized payload validation."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal, Self

import numpy as np
import numpy.typing as npt
import polars as pl
from pydantic import ConfigDict, model_validator

from avk.inputs.formats import FormatSpec, read
from avk.inputs.registry import FrozenSpec
from avk.inputs.sources import ResolvedInputs
from avk.model.data import Table
from avk.runtime.errors import ConfigError, InputError


class TabularAssumption(FrozenSpec):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    table: Table
    units: Literal["probability", "fraction", "amount", "annual_effective", "mixed"]
    fractional_age: Literal["floor", "not_applicable"]
    below: Literal["error", "clamp", "zero_rows"]
    above: Literal["error", "clamp", "zero"]
    unknown: Literal["error", "first"]

    @model_validator(mode="after")
    def valid_payload(self) -> Self:
        values = self.table.values
        if not np.isfinite(values).all():
            raise ValueError(f"{self.table.name}: non-finite assumption value")
        if self.units == "probability" and ((values < 0) | (values > 1)).any():
            raise ValueError(f"{self.table.name}: probability must be between 0 and 1")
        if self.units == "annual_effective" and (values <= -1).any():
            raise ValueError(f"{self.table.name}: annual interest must exceed -1")
        return self


class MortalityAssumption(TabularAssumption):
    kind: Literal["age_sex"]


class MorbidityAssumption(TabularAssumption):
    kind: Literal["age_sex"]


class LapseAssumption(TabularAssumption):
    kind: Literal["year_channel"]


class ExpenseAssumption(TabularAssumption):
    kind: Literal["knots", "categories", "annual_schedule"]

    def schedule(self, horizon: int) -> npt.NDArray[np.float64]:
        """An annual schedule of one value column as a monthly curve over the projection: each
        year's amount falls in its first month (months 0, 12, 24, ...), the other months hold
        zero, and nothing lies beyond the projection's last month."""
        if self.kind != "annual_schedule" or self.table.values.ndim != 2:
            raise InputError(f"{self.table.name}: only an annual schedule is a monthly curve")
        if self.table.values.shape[1] != 1:
            raise InputError(f"{self.table.name}: a curve reads exactly one value column")
        years = -(-horizon // 12)
        if self.table.values.shape[0] < years:
            raise InputError(f"{self.table.name}: not enough years for the projection term")
        monthly = np.zeros(horizon)
        monthly[::12] = self.table.values[:years, 0]
        return monthly


class CommissionAssumption(TabularAssumption):
    kind: Literal["year_channel"]


class ModalFactorAssumption(TabularAssumption):
    kind: Literal["frequency"]


class ReinsuranceAssumption(TabularAssumption):
    kind: Literal["smoker_sa_bands"]


class InterestCurveAssumption(TabularAssumption):
    kind: Literal["annual_curve"]
    valuation_month: int

    @model_validator(mode="after")
    def valid_month(self) -> Self:
        if not 1 <= self.valuation_month <= 12:
            raise ValueError("valuation_month must be between 1 and 12")
        return self

    def column(self, name: str) -> int:
        """Position of a value column, as declared by the binding that loaded the curve."""
        return self.table.axes[1].keys.index(name)

    def monthly(self, horizon: int) -> npt.NDArray[np.float64]:
        """Unshifted monthly-effective rates: one row per month, one column per field."""
        annual = np.repeat(self.table.values, 12, axis=0)[:horizon]
        if len(annual) < horizon:
            raise InputError(f"{self.table.name}: not enough years for scenario horizon")
        return np.power(1 + annual, 1 / 12) - 1


class ProductParameters(FrozenSpec):
    product_name: str
    variables: Mapping[str, float | None]

    @model_validator(mode="after")
    def freeze_values(self) -> Self:
        if not np.isfinite([v for v in self.variables.values() if v is not None]).all():
            raise ValueError("Product parameters must be finite")
        object.__setattr__(self, "variables", MappingProxyType(dict(self.variables)))
        return self

    @classmethod
    def load_product_config(cls, inputs: ResolvedInputs, product_name: str) -> Self:
        loaded = cls.load_table(inputs, product_name, 0)
        key = "parameter"
        frame = pl.DataFrame({key: loaded.axes[0].keys, product_name: loaded.values[:, 0]})
        values = frame[product_name]
        for switch in ("renewal_premium_expense_after_payment_term", "lapses_after_payment_term"):
            selected = frame.filter(pl.col(key) == switch)[product_name]
            if len(selected) and selected[0] not in (0.0, 1.0):
                raise ConfigError(f"product_parameters: {switch} must be 0 (false) or 1 (true)")
        return cls(
            product_name=product_name,
            variables=dict(zip(frame[key].to_list(), values.to_list(), strict=True)),
        )

    @staticmethod
    def load_table(inputs: ResolvedInputs, product_name: str, projection_months: int) -> Table:
        """The product's parameter column through its registered reader. NA cells for
        features the product does not use stay absent, never become zero."""
        frame = inputs.read("product_parameters")
        spec = FormatSpec(
            "product_parameters",
            {
                "logical_name": "product_parameters",
                "sha256": inputs.fingerprints["product_parameters"],
            },
            (),
            (product_name,),
            product_name,
            projection_months,
            "mixed",
        )
        return read(inputs.format_of("product_parameters"), frame, spec)

    def require(self, key: str) -> float:
        value = self.variables.get(key)
        if value is None:
            raise ConfigError(
                f"product_parameters: required variable {key!r} is missing or NA "
                f"for {self.product_name}"
            )
        if key in ("flat_mortality_be", "flat_mortality_reserving") and not 0 <= value <= 1:
            raise ConfigError(f"product_parameters: {key} must be between 0 and 1")
        return value
