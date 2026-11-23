"""The compiler front end: product classes in, a checked and scheduled `ProductIR` out.

Stateless: `build_ir` reads the definition's source and returns new objects; nothing is
cached between calls. Code generation is the emitter's job.
"""

from dataclasses import replace

from avk.model import lang
from avk.model.compiler import bases as basis_sets
from avk.model.compiler import ownership, parse
from avk.model.compiler.explain import explain
from avk.model.compiler.manifest import bound, reached
from avk.model.compiler.schedule import schedule
from avk.model.ir import DefinitionError, ProductIR

__all__ = ["DefinitionError", "bound", "build_ir", "explain"]


def build_ir(definition: type[lang.Product], *, bases: tuple[str, ...]) -> ProductIR:
    """Check, flatten, instantiate on `bases` and schedule one product definition.

    `bases` is a subset of the product's `BASES` (the run layer always passes all of them).
    Formulas are checked against the bases being built: `at_basis` must name one of them, and
    an `@on` variant for a basis outside the set is not translated.
    """
    composition = parse.read(definition)
    if not bases or len(set(bases)) != len(bases) or not set(bases) <= set(composition.bases):
        raise DefinitionError(
            composition.source,
            definition.__name__,
            "BASES",
            f"cannot compile for bases {bases}: choose distinct bases from {composition.bases}",
        )
    resolved = ownership.check(composition)

    # A component may read only the columns it defines (through its own bases) or requires.
    readable: dict[type, frozenset[str]] = {}
    for cls in composition.classes:
        if issubclass(cls, lang.Product):
            continue
        own = {
            m.name
            for m in composition.methods
            if issubclass(cls, m.owner) and not m.abstract and m.on is None
        }
        own |= {port for r in composition.requires if issubclass(cls, r.owner) for port in r.ports}
        readable[cls] = frozenset(own)
    names = parse.Names(
        columns=frozenset(resolved.columns),
        variants=frozenset(m.name for m in resolved.variants.values()),
        bindings=frozenset(resolved.bindings),
        fields=frozenset(composition.fields),
        bases=bases,
        readable=readable,
        product=definition.__name__,
    )
    formulas = {name: parse.translate(m, names) for name, m in resolved.columns.items()}
    variant_formulas = {
        key: parse.translate(m, names) for key, m in resolved.variants.items() if key[1] in bases
    }
    # Replaced definitions are checked too: a component is valid on its own, whoever uses it.
    winners = {id(m) for m in (*resolved.columns.values(), *resolved.variants.values())}
    for method in composition.methods:
        if not method.abstract and id(method) not in winners:
            parse.translate(method, names)
    quantities = basis_sets.instantiate(resolved, formulas, variant_formulas, bases)
    plan = schedule(quantities)

    # Rule 2: a state belongs to its component; only @override replaces it.
    states = {name for name, _ in plan.states}
    for (column, _basis), method in resolved.variants.items():
        if column in states:
            raise method.error(
                None, f"'{column}' is a state; only @override replaces it, never @on"
            )
    quantities = tuple(replace(q, kind="state") if q.key in plan.states else q for q in quantities)
    return ProductIR(composition.code, bases, quantities, plan.passes, reached(quantities, bases))
