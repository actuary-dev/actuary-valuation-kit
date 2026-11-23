"""Build exactly the manifest's assumptions once per run, with shared table validation."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Literal, Self

from pydantic import ConfigDict, ValidationError, model_validator

from avk.assumptions.models import (
    ExpenseAssumption,
    InterestCurveAssumption,
    ProductParameters,
    TabularAssumption,
)
from avk.inputs.formats import FormatSpec, read
from avk.inputs.policies import PreparationConfig
from avk.inputs.registry import FrozenSpec
from avk.inputs.sources import ResolvedInputs
from avk.model.data import Axis
from avk.model.lang import Above, Below, Binding, Unknown
from avk.model.manifest import Manifest
from avk.runtime.errors import ConfigError

Units = Literal["probability", "fraction", "amount", "annual_effective", "mixed"]


@dataclass(frozen=True)
class AssumptionBinding:
    """How one logical table is read, and the assumption kind that validates it."""

    logical_name: str
    columns: tuple[str, ...]
    model: type[TabularAssumption]
    kind: str
    units: Units
    below: Below
    above: Above
    unknown: Unknown = "error"
    format_name: str | None = None

    @property
    def fractional_age(self) -> Literal["floor", "not_applicable"]:
        return "floor" if self.kind == "age_sex" else "not_applicable"


def declare(
    declared: Mapping[str, Binding],
    name: str,
    model: type[TabularAssumption],
    kind: str,
    units: Units,
    *,
    columns: tuple[str, ...] | None = None,
    below: Below | None = None,
    above: Above | None = None,
    logical_name: str | None = None,
    format_name: str | None = None,
) -> AssumptionBinding:
    """Loader details for the table bound as `name` (see `model.manifest.table_bindings`).
    Rules the formulas already declare (the integer axis, unknown keys, the value column)
    are taken from there and may not be restated; anything else must be given here."""
    binding = declared.get(name)
    axes = binding.axes if binding else ()
    integer = [axis for axis in axes if axis.kind == "int"]
    if integer:
        if below is not None or above is not None:
            raise ConfigError(f"{name}: integer-axis rules are declared by the formulas")
        below, above = integer[0].below, integer[0].above
    if below is None or above is None:
        raise ConfigError(f"{name}: below and above rules must be declared")
    unknown: Unknown = "error"
    for axis in axes:
        if axis.kind == "keymap" and axis.unknown is not None:
            unknown = axis.unknown
            break
    if binding and binding.value:
        if columns is not None:
            raise ConfigError(f"{name}: the value column is declared by the formulas")
        columns = (binding.value,)
    if columns is None:
        raise ConfigError(f"{name}: value columns must be declared")
    return AssumptionBinding(
        logical_name or name, columns, model, kind, units, below, above, unknown, format_name
    )


@dataclass(frozen=True)
class ScenarioVariable:
    """One economic variable a generator derives from a bound interest curve.

    `timing` places the curve's unshifted monthly rate `raw` on projection month `t`:
    - `lag`: `raw[t - months]`, zero before month `months`;
    - `fiscal_lag`: as `lag`, with `months` reduced by the months elapsed since the
      fiscal-year start at the valuation date;
    - `fiscal_lead`: `raw[t - 1 + elapsed]` from month 1, ending one month early.
      This aligns locked-in rates to the elapsed months of the reporting year.
    """

    name: str
    curve: str
    column: str
    timing: Literal["lag", "fiscal_lag", "fiscal_lead"]
    months: int = 0
    fiscal_start_month: int | Literal["fiscal_start_month"] | None = None

    def __post_init__(self) -> None:
        if self.months < 0:
            raise ValueError(f"{self.name}: months must be nonnegative")
        fiscal = self.timing != "lag"
        if fiscal != (self.fiscal_start_month is not None):
            raise ValueError(f"{self.name}: fiscal_start_month is required only by fiscal timing")
        if isinstance(self.fiscal_start_month, int) and not 1 <= self.fiscal_start_month <= 12:
            raise ValueError(f"{self.name}: fiscal_start_month must be between 1 and 12")


@dataclass
class AssumptionSpec:
    """One run's requirements. Build a fresh spec per run: it caches validated payloads,
    which are shared across that run's basis contexts and must not reach another run."""

    product: str
    tables: Mapping[str, AssumptionBinding]
    scenario_variables: tuple[ScenarioVariable, ...] = ()
    cache: dict[str, TabularAssumption] = field(default_factory=dict)
    parameters: ProductParameters | None = None
    parameter_column: str | None = None

    def load_parameters(self, inputs: ResolvedInputs) -> ProductParameters:
        if self.parameters is None:
            self.parameters = ProductParameters.load_product_config(
                inputs, self.parameter_column or self.product
            )
        return self.parameters


class AssumptionContext(FrozenSpec):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    product: str
    basis: str
    valuation_date: date
    manifest: Manifest
    tables: Mapping[str, TabularAssumption]
    params: Mapping[str, float]
    curves: Mapping[str, ExpenseAssumption]
    source_hashes: Mapping[str, str]

    @model_validator(mode="after")
    def exact_manifest(self) -> Self:
        for name, expected in (
            ("tables", self.manifest.tables),
            ("params", self.manifest.params),
            ("curves", self.manifest.curves),
        ):
            actual = getattr(self, name)
            if set(actual) != expected:
                raise ValueError(
                    f"{self.product}/{self.basis}/{name}: expected {sorted(expected)}, "
                    f"got {sorted(actual)}"
                )
            object.__setattr__(self, name, MappingProxyType(dict(actual)))
        object.__setattr__(self, "source_hashes", MappingProxyType(dict(self.source_hashes)))
        return self


def _load(
    spec: AssumptionSpec,
    binding: AssumptionBinding,
    inputs: ResolvedInputs,
    config: PreparationConfig,
) -> TabularAssumption:
    frame = inputs.read(binding.logical_name)
    rule = Axis("binding", "int", 0, 0, binding.below, binding.above, (), None)
    fmt = FormatSpec(
        binding.logical_name,
        {"logical_name": binding.logical_name, "sha256": inputs.fingerprints[binding.logical_name]},
        (rule,),
        binding.columns,
        spec.product,
        config.projection_term * 12,
        binding.units,
    )
    selected_format = (
        inputs.location(binding.logical_name).format
        or binding.format_name
        or inputs.format_of(binding.logical_name)
    )
    loaded = read(selected_format, frame, fmt)
    fields: dict[str, Any] = {
        "kind": binding.kind,
        "units": binding.units,
        "fractional_age": binding.fractional_age,
        "below": binding.below,
        "above": binding.above,
        "unknown": binding.unknown,
    }
    if binding.model is InterestCurveAssumption:
        fields["valuation_month"] = config.valuation_date.month
    return binding.model(table=loaded, **fields)


def _cached(
    spec: AssumptionSpec, name: str, inputs: ResolvedInputs, config: PreparationConfig
) -> TabularAssumption:
    if name not in spec.cache:
        try:
            spec.cache[name] = _load(spec, spec.tables[name], inputs, config)
        except ValidationError as exc:
            raise ConfigError(f"{spec.product}: invalid assumption {name}: {exc}") from exc
    return spec.cache[name]


def load_declared(
    spec: AssumptionSpec, inputs: ResolvedInputs, config: PreparationConfig
) -> dict[str, TabularAssumption]:
    """Read and validate every table and curve the specification declares, once per run.

    This is the input gate: a product's declared inputs are checked even before a formula
    reaches them. Contexts (`build_context`) then hold only what the formulas reach and reuse
    these validated objects rather than reading again.
    """
    return {name: _cached(spec, name, inputs, config) for name in sorted(spec.tables)}


def build_context(
    spec: AssumptionSpec,
    manifest: Manifest,
    basis: str,
    inputs: ResolvedInputs,
    config: PreparationConfig,
) -> AssumptionContext:
    """The frozen context for one basis: exactly the manifest's tables, curves and parameters."""
    tables: dict[str, TabularAssumption] = {}
    curves: dict[str, ExpenseAssumption] = {}
    try:
        for name in sorted(manifest.tables | manifest.curves):
            if name not in spec.tables:
                raise ConfigError(
                    f"{spec.product}/{basis}: missing assumption specification {name}"
                )
            assumption = _cached(spec, name, inputs, config)
            if name in manifest.curves:
                # A curve a formula reads is a schedule (an interest curve feeds the generator).
                if not isinstance(assumption, ExpenseAssumption):
                    raise ConfigError(f"{spec.product}/{basis}: {name} is not a schedule")
                curves[name] = assumption
            else:
                tables[name] = assumption
        parameters = spec.load_parameters(inputs) if manifest.params else None
        params = (
            {name: parameters.require(name) for name in sorted(manifest.params)}
            if parameters
            else {}
        )
        names = {spec.tables[name].logical_name for name in manifest.tables | manifest.curves}
        if params:
            names.add("product_parameters")
        return AssumptionContext(
            product=spec.product,
            basis=basis,
            valuation_date=config.valuation_date,
            manifest=manifest,
            tables=tables,
            params=params,
            curves=curves,
            source_hashes={name: inputs.fingerprints[name] for name in names},
        )
    except ValidationError as exc:
        raise ConfigError(f"{spec.product}/{basis}: invalid assumption context: {exc}") from exc
