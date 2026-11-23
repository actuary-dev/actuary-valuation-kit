"""Basis instantiation: each column once per basis, or once when every basis lowers it the same.

A column exists per basis when its lowered formula differs between bases (a `by_basis`
binding, an `@on` variant) or when it reads, on its own basis, a column that does. Reading
another basis explicitly (`at_basis`) does not make a column basis-specific.
"""

from avk.model import lang
from avk.model.compiler.ownership import Resolved
from avk.model.compiler.parse import Method, Ref, Use
from avk.model.ir import (
    Bound,
    Col,
    Const,
    DefinitionError,
    Dep,
    Field,
    Lookup,
    Node,
    Param,
    Quantity,
    RunParam,
    SourceRef,
    transform,
    walk,
)

KIND_WORDS = {"tables": "table", "scen_vars": "scenario variable", "curves": "curve"}


def _binding_value(resolved: Resolved, attr: str, basis: str) -> lang.Binding | float:
    declared = resolved.bindings[attr]
    value: lang.Binding | lang.BasisBinding | float = declared.value
    if isinstance(value, lang.BasisBinding):
        if basis not in value.per_basis:
            raise DefinitionError(
                declared.source,
                declared.owner.__name__,
                attr,
                f"by_basis gives no binding for basis '{basis}'",
            )
        value = value.per_basis[basis]
    if isinstance(value, lang.Binding):
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DefinitionError(
            declared.source,
            declared.owner.__name__,
            attr,
            f"a by_basis value is a binding or a number, not {value!r}",
        )
    return float(value)


def _lower_use(use: Use, basis: str, resolved: Resolved, method: Method) -> Node:
    def fail(reason: str) -> DefinitionError:
        return DefinitionError(
            SourceRef(method.source.file, use.line), method.owner.__name__, method.name, reason
        )

    value = _binding_value(resolved, use.attr, basis)
    if not isinstance(value, lang.Binding):
        if use.index is not None:
            raise fail(f"'{use.attr}' is the constant {value!r} on basis '{basis}'; not indexed")
        return Const(value)
    if value.kind == "params":
        if use.index is not None:
            raise fail(f"parameter {value.name} is a scalar; it is not indexed")
        return Param(value.name)
    if value.kind == "run_params":
        if value.axes:
            if use.index is None or len(use.index) != 1:
                raise fail(f"monthly run parameter {value.name} is read with one index")
            return Lookup(value.kind, value.name, use.index)
        if use.index is not None:
            raise fail(f"run parameter {value.name} is a scalar; it is not indexed")
        return RunParam(value.name)
    if use.index is None:
        raise fail(
            f"{KIND_WORDS[value.kind]} {value.name} is read with an index: self.{use.attr}[...]"
        )
    if value.kind == "tables":
        if len(use.index) != len(value.axes):
            raise fail(
                f"table {value.name} has {len(value.axes)} axes but is indexed with "
                f"{len(use.index)}"
            )
        # Every axis names what indexes it, once, where it is bound.
        for axis, index in zip(value.axes, use.index, strict=True):
            if axis.kind == "keymap" and index != Field(axis.field):
                raise fail(
                    f"keymap axis '{axis.field}' of table {value.name} must be indexed by "
                    f"self.policy.{axis.field} (keys are mapped per policy before the kernel)"
                )
            if axis.kind == "int" and index not in (
                Ref(axis.field, None, 0, None),
                Field(axis.field),
            ):
                raise fail(
                    f"integer axis '{axis.field}' of table {value.name} must be indexed by "
                    f"self.{axis.field}(t) or self.policy.{axis.field}"
                )
    elif len(use.index) != 1:
        raise fail(f"{KIND_WORDS[value.kind]} {value.name} takes one index")
    elif value.kind == "curves" and not value.axes:
        raise fail(
            f"curve {value.name} is read without out-of-range rules: bind it with "
            "curve(name, below=..., above=...)"
        )
    return Lookup(value.kind, value.name, use.index)


def _deps(expr: Node) -> tuple[Dep, ...]:
    found = [
        Dep(node.name, node.basis, node.offset) for node in walk(expr) if isinstance(node, Col)
    ]
    return tuple(dict.fromkeys(found))


def instantiate(
    resolved: Resolved,
    formulas: dict[str, Node],
    variant_formulas: dict[tuple[str, str], Node],
    bases: tuple[str, ...],
) -> tuple[Quantity, ...]:
    def method(name: str, basis: str) -> Method:
        return resolved.variants.get((name, basis), resolved.columns[name])

    lowered: dict[str, dict[str, Node]] = {}
    for name in resolved.columns:
        lowered[name] = {}
        for basis in bases:
            formula = variant_formulas.get((name, basis), formulas[name])
            owner = method(name, basis)

            def lower(node: Node, basis: str = basis, owner: Method = owner) -> Node:
                return _lower_use(node, basis, resolved, owner) if isinstance(node, Use) else node

            lowered[name][basis] = transform(formula, lower)

    specific = {name for name, per_basis in lowered.items() if len(set(per_basis.values())) > 1}
    same_basis = {
        name: {
            node.name
            for expr in per_basis.values()
            for node in walk(expr)
            if isinstance(node, Ref) and node.basis is None
        }
        for name, per_basis in lowered.items()
    }
    changed = True
    while changed:
        changed = False
        for name, targets in same_basis.items():
            if name not in specific and targets & specific:
                specific.add(name)
                changed = True

    def finalize(expr: Node, basis: str | None) -> Node:
        def resolve(node: Node) -> Node:
            if not isinstance(node, Ref):
                return node
            target = node.basis if node.basis is not None else basis
            return Col(
                node.name, target if node.name in specific else None, node.offset, node.default
            )

        return transform(expr, resolve)

    quantities: list[Quantity] = []
    for name in resolved.columns:
        instances: tuple[str | None, ...] = bases if name in specific else (None,)
        for instance in instances:
            definition = method(name, instance or bases[0])
            expr = finalize(lowered[name][instance or bases[0]], instance)
            quantities.append(
                Quantity(
                    name,
                    instance,
                    definition.owner.__name__,
                    expr,
                    _deps(expr),
                    "policy",
                    (),
                    "formula",
                    definition.source,
                    definition.doc,
                )
            )

    for attr, declared in resolved.bindings.items():
        per_basis = {basis: _binding_value(resolved, attr, basis) for basis in bases}
        shared = len(set(per_basis.values())) == 1
        for basis, value in per_basis.items():
            if not isinstance(value, lang.Binding):
                continue
            quantities.append(
                Quantity(
                    attr,
                    None if shared else basis,
                    declared.owner.__name__,
                    Bound(value.kind, value.name, value.value, value.axes),
                    (),
                    "policy",
                    (),
                    "binding",
                    declared.source,
                    "",
                )
            )
            if shared:
                break
    return tuple(quantities)
