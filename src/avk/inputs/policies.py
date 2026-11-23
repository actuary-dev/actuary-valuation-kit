"""Vectorized model-point preparation, separate from projection formulas.

Product-specific adapters live with their product (`products/<family>/preparation.py`).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Protocol

import polars as pl

from avk.model.data import ModelPoints
from avk.runtime.errors import InputError


class PreparationConfig(Protocol):
    @property
    def valuation_date(self) -> date: ...

    @property
    def projection_term(self) -> int: ...

    @property
    def run_type(self) -> str: ...

    @property
    def products_to_run(self) -> tuple[str, ...]: ...


def numeric(column: str) -> pl.Expr:
    return pl.col(column).cast(pl.String).str.replace_all(",", "").cast(pl.Float64, strict=False)


def dates(column: str, dtype: pl.DataType) -> pl.Expr:
    if dtype.is_temporal():
        return pl.col(column).cast(pl.Date)
    text = pl.col(column).cast(pl.String)
    return pl.coalesce(
        text.str.to_date("%d/%m/%Y", strict=False),
        text.str.to_date("%d-%m-%Y", strict=False),
        text.str.to_date("%Y-%m-%d", strict=False),
        text.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False).cast(pl.Date),
        text.str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False).cast(pl.Date),
    )


class ModelPointAdapter(ABC):
    """Prepares one product's policy rows; built per run from that run's loaded tables."""

    code: str
    table: str

    @abstractmethod
    def prepare(
        self, frame: pl.DataFrame, config: PreparationConfig
    ) -> ModelPoints[pl.DataFrame]: ...

    @abstractmethod
    def product_codes(self, frame: pl.DataFrame) -> pl.Series: ...

    def with_fields(self, **fields: str) -> "ModelPointAdapter":
        """Return a fresh adapter with explicitly mapped numeric input fields."""
        return ExtendedModelPointAdapter(self, fields)

    def dispatched_codes(self, frame: pl.DataFrame, config: PreparationConfig) -> pl.Series:
        """Product codes, after proving every row is requested and belongs to this adapter."""
        codes = self.product_codes(frame)
        if codes.is_null().any() or (~codes.is_in(config.products_to_run)).any():
            raise InputError(f"{self.table}: product code not in Products_to_run")
        if (codes != self.code).any():
            raise InputError(f"{self.table}: product code does not match the {self.code} factory")
        return codes


class ExtendedModelPointAdapter(ModelPointAdapter):
    """Strict vectorized field extension; the wrapped product owns preparation rules."""

    def __init__(self, adapter: ModelPointAdapter, fields: Mapping[str, str]) -> None:
        self.adapter = adapter
        self.code, self.table = adapter.code, adapter.table
        self.extra_fields = MappingProxyType(dict(fields))

    def product_codes(self, frame: pl.DataFrame) -> pl.Series:
        return self.adapter.product_codes(frame)

    def prepare(self, frame: pl.DataFrame, config: PreparationConfig) -> ModelPoints[pl.DataFrame]:
        missing = set(self.extra_fields.values()) - set(frame.columns)
        if missing:
            raise InputError(f"{self.table}: missing required columns {sorted(missing)}")
        extra = frame.select(
            numeric(source).alias(name) for name, source in self.extra_fields.items()
        )
        for name, source in self.extra_fields.items():
            if extra[name].null_count() or not extra[name].is_finite().all():
                raise InputError(f"{self.table}: {source} must contain finite numeric values")
        points = self.adapter.prepare(frame, config)
        return ModelPoints(
            points.frame.with_columns(extra),
            tuple(dict.fromkeys((*points.fields, *self.extra_fields))),
        )
