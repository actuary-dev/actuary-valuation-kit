"""Checks for formula ownership, ports, bindings, scope and dimensions.

Base-class order never decides which formula wins: a column has one owner, or its
most-derived definition is marked `@override` and derives from every other definer.
"""

from dataclasses import dataclass

from avk.model import lang
from avk.model.compiler.parse import Composition, Declared, Method, owners
from avk.model.ir import DefinitionError

KINDS = {
    "tables": "table",
    "params": "param",
    "run_params": "run_param",
    "scen_vars": "scen",
    "curves": "curve",
}


@dataclass(frozen=True)
class Resolved:
    """The winning definitions, in definition order (base components first)."""

    columns: dict[str, Method]
    variants: dict[tuple[str, str], Method]  # (column, basis) -> the `@on` method
    bindings: dict[str, Declared]


def describe(value: lang.Binding | lang.BasisBinding | float) -> str:
    if isinstance(value, lang.BasisBinding):
        parts = ", ".join(f"{basis}={describe(item)}" for basis, item in value.per_basis.items())
        return f"by_basis({parts})"
    if isinstance(value, lang.Binding):
        return f"{KINDS[value.kind]} {value.name}"
    return repr(value)


def _single_owner(definers: list[Method], label: str) -> Method:
    """Rule 1: the most-derived definition wins only if it derives from, and overrides, the rest."""
    winner = definers[0]
    for other in definers[1:]:
        if not issubclass(winner.owner, other.owner):
            raise winner.error(
                None,
                f"also defined by {other.owner.__name__}.{label}; base-class order would decide "
                "which formula wins (define it once, or replace it with @override in a class "
                "derived from both)",
            )
        if not winner.is_override:
            raise winner.error(None, f"redefines {other.owner.__name__}.{label} without @override")
    return winner


def check(composition: Composition) -> Resolved:
    product = composition.definition
    methods = composition.methods
    for method in methods:
        if method.scope != "policy":
            raise method.error(
                None,
                f"scope {method.scope!r} is not supported until time-major execution exists "
                "(every column has policy scope)",
            )
        if method.dims:
            raise method.error(
                None,
                f"named dimensions are not supported until vector lowering exists: {method.dims}",
            )
        if method.abstract and not issubclass(method.owner, lang.Product):
            raise method.error(
                None,
                "a component's ports go in REQUIRES, never @abstractmethod (a mixin listed "
                "first would shadow the implementation)",
            )

    # Rule 1 (and 2: a state is a column, so only @override replaces it).
    order: list[str] = []
    for cls in reversed(composition.classes):
        for method in methods:
            if method.owner is cls and not method.abstract and method.on is None:
                if method.name not in order:
                    order.append(method.name)
    columns = {name: _single_owner(owners(methods, name), name) for name in order}
    for method in methods:
        if (
            method.is_override
            and method.on is None
            and not any(
                other.name == method.name and other.on is None and other.owner is not method.owner
                for other in methods
                if issubclass(method.owner, other.owner)
            )
        ):
            raise method.error(None, "@override, but no inherited definition to replace")

    # Rule 3: basis-specific structure.
    found: dict[tuple[str, str], list[Method]] = {}
    for method in methods:
        if method.on is None:
            continue
        if not (
            isinstance(method.on, tuple)
            and len(method.on) == 2
            and all(isinstance(item, str) for item in method.on)
        ):
            raise method.error(None, "@on takes (basis, overrides=column)")
        basis, target = method.on
        if basis not in composition.bases:
            raise method.error(
                None, f"@on basis '{basis}' is not one of the product's BASES {composition.bases}"
            )
        if target not in columns:
            raise method.error(None, f"@on overrides '{target}', which is not a column")
        if method.name in columns:
            raise method.error(
                None,
                f"a basis variant needs its own name (for example {target}_{basis}); "
                f"'{method.name}' is a column",
            )
        found.setdefault((target, basis), []).append(method)
    variants = {
        key: _single_owner(definers, f"@on({key[1]!r}, overrides={key[0]!r})")
        for key, definers in found.items()
    }

    # Rule 4: one binding per name, one rule set per table.
    bindings: dict[str, Declared] = {}
    tables: dict[str, tuple[lang.Binding, Declared]] = {}
    runtime_shapes: dict[str, tuple[bool, Declared]] = {}
    curves: dict[str, Declared] = {}
    for declared in composition.bindings:  # most-derived class first
        if declared.name in columns or declared.name == "policy":
            raise _binding_error(declared, f"'{declared.name}' is both a binding and a column")
        first = bindings.setdefault(declared.name, declared)
        if first.value != declared.value:
            raise _binding_error(
                first,
                f"binds '{declared.name}' to {describe(first.value)}, but "
                f"{declared.owner.__name__} binds it to {describe(declared.value)}",
            )
        values = (
            declared.value.per_basis.values()
            if isinstance(declared.value, lang.BasisBinding)
            else (declared.value,)
        )
        for value in values:
            if isinstance(value, lang.Binding) and value.kind == "run_params":
                monthly = bool(value.axes)
                shape = runtime_shapes.setdefault(value.name, (monthly, declared))
                if shape[0] != monthly:
                    raise _binding_error(
                        declared,
                        f"run parameter {value.name} is bound as both scalar and monthly",
                    )
            if isinstance(value, lang.Binding) and value.kind == "curves":
                curves.setdefault(value.name, declared)
            if isinstance(value, lang.Binding) and value.kind == "tables":
                seen = tables.setdefault(value.name, (value, declared))
                if seen[0] != value:
                    raise _binding_error(
                        seen[1],
                        f"table {value.name} is bound with different rules by "
                        f"{declared.owner.__name__}.{declared.name}",
                    )
    for name, (monthly, declared) in runtime_shapes.items():
        assumption_kind = "curve" if name in curves else "table" if name in tables else None
        if monthly and assumption_kind is not None:
            raise _binding_error(
                declared,
                f"monthly run parameter {name} conflicts with assumption {assumption_kind} {name}",
            )
    if "policy" in columns:
        raise columns["policy"].error(None, "'policy' is reserved for model-point fields")

    # Component ports.
    for requires in composition.requires:
        for port in requires.ports:
            if port not in columns:
                raise DefinitionError(
                    requires.source,
                    requires.owner.__name__,
                    port,
                    f"required port is not defined by any component of {product.__name__}",
                )

    # Family ports: what Python's ABC machinery would refuse to instantiate.
    for name in sorted(getattr(product, "__abstractmethods__", ())):
        family = next(
            (m.owner.__name__ for m in methods if m.name == name and m.abstract), "the family"
        )
        raise DefinitionError(
            composition.source,
            product.__name__,
            name,
            f"family port {family}.{name} is not implemented",
        )

    # Definition order: base components first, then source lines.
    rank = {cls: index for index, cls in enumerate(composition.classes)}
    ordered = sorted(bindings.values(), key=lambda d: (-rank[d.owner], d.source.line))
    return Resolved(columns, variants, {declared.name: declared for declared in ordered})


def _binding_error(declared: Declared, reason: str) -> DefinitionError:
    return DefinitionError(declared.source, declared.owner.__name__, declared.name, reason)
