"""Definition-layer factories selected by product code, including company entry points."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from importlib.metadata import entry_points

import polars as pl

from avk.assumptions.context import AssumptionSpec
from avk.inputs.policies import ModelPointAdapter
from avk.inputs.validation import PolicyValidator
from avk.model.data import Table
from avk.model.lang import Product
from avk.outputs.schema import OutputSchema
from avk.products.diagnostics import ProductDiagnostics
from avk.runtime.errors import ConfigError


class ProductFactory(ABC):
    """Everything the run layer needs about one product code. Factories are stateless:
    per-run objects (the assumption spec, the adapter) are returned new on every call."""

    code: str
    policy_table: str  # logical name of the product's model-point table
    # Logical names of extra policy-level tables (for example fund holdings). The run reads
    # each once, validates it with `validator().validate_companions` and builds the adapter
    # with `companion_adapter` instead of `model_point_adapter`.
    companion_tables: tuple[str, ...] = ()

    @abstractmethod
    def definition(self, extensions: tuple[str, ...] = ()) -> type[Product]: ...

    @abstractmethod
    def model_point_adapter(self, tables: Mapping[str, Table]) -> ModelPointAdapter:
        """An adapter over this run's validated tables (from its assumption contexts)."""

    def companion_adapter(
        self, tables: Mapping[str, Table], companions: Mapping[str, pl.DataFrame]
    ) -> ModelPointAdapter:
        """An adapter over this run's validated tables and companion policy tables."""
        raise ConfigError(f"{self.code}: companion tables need a companion adapter")

    @abstractmethod
    def assumption_spec(self) -> AssumptionSpec: ...

    @abstractmethod
    def output_schema(self, run_type: str) -> OutputSchema: ...

    @abstractmethod
    def validator(self) -> PolicyValidator: ...

    def aggregate_ratios(self, schema: OutputSchema) -> dict[str, tuple[str, str, str, float]]:
        """Book ratios: numerator, denominator, basis and numerator sign.

        Numerators are held amounts (including product reserve floors), never policy ratios.
        """
        sources = {
            "gross_reserve_pp": ("gross_reserve_amount", 1.0),
            "net_reserve_pp": ("net_reserve_amount", 1.0),
            "bel_pp": ("bel", -1.0),
            "ifrs_bel_pp": ("ifrs_bel", 1.0),
        }
        return {
            output: (
                sources[column][0],
                "eligible_reserve_lives",
                basis or "be",
                sources[column][1],
            )
            for output, column, basis in schema.entries
            if column in sources
        }

    def diagnostics(self) -> ProductDiagnostics:
        """Parity dumps; the default writes none."""
        return ProductDiagnostics()


class ProductRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProductFactory] = {}

    def register(self, factory: ProductFactory) -> None:
        if not isinstance(factory, ProductFactory) or not factory.code:
            raise ConfigError("A product factory must provide a nonempty code")
        if not getattr(factory, "policy_table", None):
            raise ConfigError(f"{factory.code}: a product factory must name its policy table")
        if factory.code in self._factories:
            raise ConfigError(f"Duplicate product code: {factory.code}")
        self._factories[factory.code] = factory

    def for_code(self, code: str) -> ProductFactory:
        try:
            return self._factories[code]
        except KeyError as exc:
            raise ConfigError(f"Unknown product code: {code}") from exc

    def codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    @classmethod
    def default(cls) -> "ProductRegistry":
        from avk.products.credit_life.factory import CreditLifeFactory
        from avk.products.rider.factory import (
            AccidentalDeathFactory,
            CriticalIllnessFactory,
            DisabilityFactory,
        )
        from avk.products.term.factory import TermFactory
        from avk.products.unit_linked.factory import UnitLinkedFactory

        registry = cls()
        registry.register(TermFactory())
        registry.register(AccidentalDeathFactory())
        registry.register(CriticalIllnessFactory())
        registry.register(DisabilityFactory())
        registry.register(CreditLifeFactory())
        registry.register(UnitLinkedFactory())
        for entry in entry_points(group="avk.products"):
            try:
                loaded = entry.load()
                registry.register(loaded() if isinstance(loaded, type) else loaded)
            except Exception as exc:
                raise ConfigError(f"Cannot load product entry point {entry.name}: {exc}") from exc
        return registry
