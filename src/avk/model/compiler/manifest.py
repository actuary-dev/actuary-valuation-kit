"""Requirement manifests derived from the formula graph: nothing is listed by hand.

`reached` is what each basis's formulas read: the assumption context holds exactly that.
`bound` is everything the definition binds, reached or not: what the input gate validates.
"""

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from avk.model.ir import Bound, Field, Lookup, Param, ProductIR, Quantity, RunParam, walk
from avk.model.manifest import Manifest

GROUPS = ("tables", "params", "run_params", "scen_vars", "curves", "fields")


def _manifest(groups: Mapping[str, set[str]]) -> Manifest:
    return Manifest(**{group: frozenset(groups[group]) for group in GROUPS})


def _read(quantities: Iterable[Quantity]) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {group: set() for group in GROUPS}
    for quantity in quantities:
        if quantity.kind == "binding":
            continue
        for node in walk(quantity.expr):
            if isinstance(node, Lookup):
                groups[node.kind].add(node.name)
            elif isinstance(node, Param):
                groups["params"].add(node.name)
            elif isinstance(node, RunParam):
                groups["run_params"].add(node.name)
            elif isinstance(node, Field):
                groups["fields"].add(node.name)
    return groups


def reached(quantities: tuple[Quantity, ...], bases: tuple[str, ...]) -> Mapping[str, Manifest]:
    return MappingProxyType(
        {
            basis: _manifest(_read(q for q in quantities if q.basis in (None, basis)))
            for basis in bases
        }
    )


def bound(ir: ProductIR) -> Manifest:
    """Every binding on any basis; fields are those the formulas read (fields are not bound)."""
    groups: dict[str, set[str]] = {group: set() for group in GROUPS}
    for quantity in ir.quantities:
        if isinstance(quantity.expr, Bound):
            groups[quantity.expr.kind].add(quantity.expr.name)
    for manifest in ir.manifest.values():
        groups["fields"] |= manifest.fields
    return _manifest(groups)
