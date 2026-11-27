"""The authoring API: components, products, bindings and formula constructs.

Formulas are read from their source by `avk.model.compiler`; they are never called. The
construct functions below exist so formula modules import real names, and raise if executed.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal, NoReturn
from typing import override as override  # re-exported: replacing an inherited column

# Attributes the decorators set on a formula method; the compiler reads them.
ON = "__avk_on__"
SCOPE = "__avk_scope__"
DIMS = "__avk_dims__"


class Component(ABC):  # noqa: B024 - mixins must not shadow family abstract ports
    """A reusable formula mixin: `(self, t)` methods are columns, class attributes are bindings,
    and `REQUIRES` lists the columns it reads but does not own."""


class Product(Component):
    """A composition belonging to a product family."""

    # Every concrete product declares these; FIELDS are the model-point fields it reads.
    CODE: ClassVar[str]
    LABEL: ClassVar[str]
    BASES: ClassVar[tuple[str, ...]]
    FIELDS: ClassVar[tuple[str, ...]]


class ProtectionProduct(Product):
    """The protection family (Term).

    The family declares abstract ports. The net cashflow reads `premium_income`,
    `acquisition_cost`, `expense_outgo` and `benefit_outgo`. IFRS 17 uses
    `coverage_units` to allocate CSM release. Variants and regimes read these ports
    directly.
    """

    @abstractmethod
    def premium_income(self, t: float) -> float:
        """Premiums received in the month, for the lives in force."""

    @abstractmethod
    def acquisition_cost(self, t: float) -> float:
        """Costs of acquiring the business: commissions and initial expenses."""

    @abstractmethod
    def expense_outgo(self, t: float) -> float:
        """Maintenance expenses paid at the start of the month (claim expenses are separate)."""

    @abstractmethod
    def benefit_outgo(self, t: float) -> float:
        """Total benefits paid in the month: death, surrender and any other benefit."""

    @abstractmethod
    def coverage_units(self, t: float) -> float:
        """Benefit amount in force for insurance service in the month."""


class LoanLinkedProduct(Product):
    """Loan-linked family: cashflow ports consumed by shared reserving components."""

    @abstractmethod
    def premium_income(self, t: float) -> float:
        """Premium income for opening lives."""

    @abstractmethod
    def acquisition_cost(self, t: float) -> float:
        """Commission and initial expense."""

    @abstractmethod
    def expense_outgo(self, t: float) -> float:
        """Maintenance expense."""

    @abstractmethod
    def benefit_outgo(self, t: float) -> float:
        """Death and surrender benefits."""

    @abstractmethod
    def coverage_units(self, t: float) -> float:
        """Outstanding insured loan cover in force."""


class UnitLinkedProduct(Product):
    """Unit-linked family: cashflow and reserve ports of the unit segment."""

    @abstractmethod
    def premium_income(self, t: float) -> float:
        """Premiums received for opening active lives."""

    @abstractmethod
    def charge_income(self, t: float) -> float:
        """Charges received from premiums and the unit funds."""

    @abstractmethod
    def non_unit_benefit_outgo(self, t: float) -> float:
        """Benefits and additions payable by the general fund."""

    @abstractmethod
    def acquisition_cost(self, t: float) -> float:
        """Commission and initial expenses."""

    @abstractmethod
    def expense_outgo(self, t: float) -> float:
        """Maintenance expenses."""

    @abstractmethod
    def coverage_units(self, t: float) -> float:
        """Quantity of service provided, for IFRS 17."""

    @abstractmethod
    def unit_reserve(self, t: float) -> float:
        """Expected value of the closing funds across policy states."""


class RiderProduct(Product):
    """Rider family: benefits, premiums, insured events and coverage units."""

    @abstractmethod
    def benefit_outgo(self, t: float) -> float:
        """Benefits paid on the insured event and any waiver."""

    @abstractmethod
    def premium_income(self, t: float) -> float:
        """Rider premiums received."""

    @abstractmethod
    def rider_event(self, t: float) -> float:
        """The rider's insured event, resolved by composition."""

    @abstractmethod
    def coverage_units(self, t: float) -> float:
        """Units of rider cover in force."""


Below = Literal["error", "clamp", "zero_rows"]
Above = Literal["error", "clamp", "zero"]
Unknown = Literal["error", "first"]


@dataclass(frozen=True)
class AxisRule:
    field: str
    kind: Literal["int", "keymap"]
    below: Below | None
    above: Above
    unknown: Unknown | None


def int_axis(field: str, *, below: Below, above: Above) -> AxisRule:
    if below not in {"error", "clamp", "zero_rows"} or above not in {"error", "clamp", "zero"}:
        raise ValueError("Invalid integer axis rule")
    return AxisRule(field, "int", below, above, None)


def keymap(field: str, *, unknown: Unknown, above: Above) -> AxisRule:
    if unknown not in {"error", "first"} or above not in {"error", "clamp", "zero"}:
        raise ValueError("Invalid keymap rule")
    return AxisRule(field, "keymap", None, above, unknown)


@dataclass(frozen=True)
class Binding:
    kind: Literal["tables", "params", "run_params", "scen_vars", "curves"]
    name: str
    value: str | None = None
    axes: tuple[AxisRule, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                f"A binding names its source with a nonempty string, not {self.name!r}"
            )
        if self.value is not None and not isinstance(self.value, str):
            raise ValueError(f"{self.name}: value names a column with a string")
        axes = tuple(self.axes)  # a list is accepted and frozen
        if not all(isinstance(axis, AxisRule) for axis in axes):
            raise ValueError(f"{self.name}: axes are int_axis(...) or keymap(...) rules")
        object.__setattr__(self, "axes", axes)


@dataclass(frozen=True)
class BasisBinding:
    per_basis: Mapping[str, Binding | float]


def table(name: str, *, value: str | None = None, axes: tuple[AxisRule, ...]) -> Binding:
    return Binding("tables", name, value, axes)


def param(name: str) -> Binding:
    return Binding("params", name)


def run_param(name: str, *, monthly: bool = False) -> Binding:
    """A numeric parameter the run type sets, never product data. Scalars are read directly;
    monthly=True supplies a finite monthly vector, read with one index and clamped at its
    endpoints. Every case and run type shares one compiled composition."""
    axes = (AxisRule("month", "int", "clamp", "clamp", None),) if monthly else ()
    return Binding("run_params", name, axes=axes)


def scen(name: str) -> Binding:
    return Binding("scen_vars", name)


def curve(name: str, *, below: Below | None = None, above: Above | None = None) -> Binding:
    """A monthly schedule `self.crv[i]`, built from its assumption before the kernel and read
    at any integer month `i`. A formula that reads it needs both out-of-range rules: `clamp`
    (the first or last month) or zero (`below="zero_rows"`, `above="zero"`); an index is never
    proven in range, so `error` is rejected. Without rules the curve is only an input of the
    scenario generator (an interest curve)."""
    if (below is None) != (above is None):
        raise ValueError(f"{name}: a curve declares both out-of-range rules or neither")
    if below is None or above is None:
        return Binding("curves", name)
    if below not in {"clamp", "zero_rows"} or above not in {"clamp", "zero"}:
        raise ValueError(f"{name}: a curve's out-of-range rules are clamp or zero, never error")
    return Binding("curves", name, axes=(AxisRule("month", "int", below, above, None),))


def by_basis(**per_basis: Binding | float) -> BasisBinding:
    return BasisBinding(MappingProxyType(dict(per_basis)))


type Formula = Callable[..., float]


def _mark[F: Formula](attribute: str, value: object) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        setattr(function, attribute, value)
        return function

    return decorate


def on[F: Formula](basis: str, *, overrides: str) -> Callable[[F], F]:
    """Replace column `overrides` on `basis` only: a structural difference between bases."""
    return _mark(ON, (basis, overrides))


def scope[F: Formula](kind: str) -> Callable[[F], F]:
    """Declare a column's scope. Only `"policy"` is supported until time-major execution."""
    return _mark(SCOPE, kind)


def dims[F: Formula](*names: str) -> Callable[[F], F]:
    """Declare named dimensions. None are supported until vector lowering exists."""
    return _mark(DIMS, names)


def _compiled(name: str) -> NoReturn:
    raise TypeError(f"{name}() is a formula construct: formulas are compiled, not called")


def prev(column: Formula, default: float) -> float:
    """The column's value last month; `default` at month 0."""
    _compiled("prev")


def nxt(column: Formula, default: float) -> float:
    """The column's value next month; `default` at the last month."""
    _compiled("nxt")


def at_basis(basis: str, column: Formula) -> Formula:
    """The column on a named basis: call it with `(t)`, or pass it to `prev`/`nxt`."""
    _compiled("at_basis")


def if_(condition: float, then: float, otherwise: float) -> float:
    """`then` where `condition` is nonzero, else `otherwise`."""
    _compiled("if_")


def clip(value: float, lower: float, upper: float) -> float:
    _compiled("clip")


def floor(value: float) -> float:
    _compiled("floor")


def exp(value: float) -> float:
    _compiled("exp")


def log(value: float) -> float:
    _compiled("log")


def sqrt(value: float) -> float:
    _compiled("sqrt")


def fma(a: float, b: float, c: float) -> float:
    """Exactly rounded a*b+c, for the CREDIT_LIFE loan recurrence."""
    _compiled("fma")
