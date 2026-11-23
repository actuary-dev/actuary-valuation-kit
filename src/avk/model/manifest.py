"""Requirement manifests (derived by `model.compiler` from the formulas) and table bindings."""

from dataclasses import dataclass

from avk.model.lang import BasisBinding, Binding, Product


@dataclass(frozen=True)
class Manifest:
    tables: frozenset[str]
    params: frozenset[str]
    scen_vars: frozenset[str]
    curves: frozenset[str]
    fields: frozenset[str]
    run_params: frozenset[str] = frozenset()


def table_bindings(definition: type[Product]) -> dict[str, Binding]:
    """Every table and curve binding on any basis: the single declaration of its lookup rules."""
    attributes: dict[str, object] = {}
    for cls in reversed(definition.__mro__):
        attributes.update(vars(cls))
    found: dict[str, Binding] = {}
    for item in attributes.values():
        candidates = item.per_basis.values() if isinstance(item, BasisBinding) else (item,)
        for binding in candidates:
            if isinstance(binding, Binding) and binding.kind in ("tables", "curves"):
                if found.setdefault(binding.name, binding) != binding:
                    raise ValueError(
                        f"{definition.__name__}: conflicting bindings for {binding.name}"
                    )
    return found
