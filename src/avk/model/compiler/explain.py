"""A deterministic, reviewable account of a `ProductIR` (`avk compile --explain`).

Plain ASCII, no file paths, line numbers or docstrings, so the text changes only when the
formulas, their schedule or their requirements change.
"""

from avk.model.compiler.manifest import GROUPS, bound
from avk.model.ir import (
    BinOp,
    BoolOp,
    Bound,
    Call,
    Col,
    Compare,
    Const,
    Field,
    Lookup,
    Node,
    Param,
    ProductIR,
    RunParam,
    Time,
    UnaryOp,
)
from avk.model.manifest import Manifest

PRECEDENCE = {"or": 1, "and": 2, "not": 3, "compare": 4, "+": 5, "-": 5}
PRECEDENCE |= {"*": 6, "/": 6, "//": 6, "%": 6, "unary": 7, "**": 8, "atom": 9}
WORDS = {
    "tables": "table",
    "params": "param",
    "run_params": "run_param",
    "scen_vars": "scen",
    "curves": "curve",
}


def _number(value: float) -> str:
    return str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)


def render(node: Node, parent: int = 0) -> str:
    text, own = _render(node)
    return f"({text})" if own < parent else text


def _render(node: Node) -> tuple[str, int]:
    atom = PRECEDENCE["atom"]
    match node:
        case Const(value):
            return _number(value), atom
        case Time():
            return "t", atom
        case Field(name):
            return f"policy.{name}", atom
        case Param(name):
            return f'param("{name}")', atom
        case RunParam(name):
            return f'run_param("{name}")', atom
        case Lookup(kind, name, index):
            return f'{WORDS[kind]}("{name}")[{", ".join(render(i) for i in index)}]', atom
        case Col(name, basis, offset, default):
            label = name if basis is None else f"{name}@{basis}"
            if offset == 0:
                return label, atom
            assert default is not None
            return f"{'prev' if offset < 0 else 'nxt'}({label}, {render(default)})", atom
        case BinOp(op, left, right):
            own = PRECEDENCE[op]
            if op == "**":
                return f"{render(left, own + 1)} ** {render(right, own)}", own
            return f"{render(left, own)} {op} {render(right, own + 1)}", own
        case UnaryOp("not", operand):
            return f"not {render(operand, PRECEDENCE['not'])}", PRECEDENCE["not"]
        case UnaryOp(op, operand):
            return f"{op}{render(operand, PRECEDENCE['unary'])}", PRECEDENCE["unary"]
        case Compare(op, left, right):
            own = PRECEDENCE["compare"]
            return f"{render(left, own + 1)} {op} {render(right, own + 1)}", own
        case BoolOp(op, values):
            own = PRECEDENCE[op]
            return f" {op} ".join(render(value, own + 1) for value in values), own
        case Call(fn, args):
            return f"{fn}({', '.join(render(arg) for arg in args)})", atom
        case Bound(kind, name, value, axes):
            rules = ", ".join(
                f"{axis.field}: {axis.kind}"
                + (f" below={axis.below}" if axis.below else "")
                + f" above={axis.above}"
                + (f" unknown={axis.unknown}" if axis.unknown else "")
                for axis in axes
            )
            extra = (f', value="{value}"' if value else "") + (f", axes=({rules})" if axes else "")
            return f'{WORDS[kind]}("{name}"{extra})', atom
    raise TypeError(f"cannot render {type(node).__name__}")


def _groups(manifest: Manifest, indent: str) -> list[str]:
    return [
        f"{indent}{group + ':':<12}{', '.join(sorted(getattr(manifest, group))) or '-'}"
        for group in GROUPS
    ]


def explain(ir: ProductIR) -> str:
    formulas = {q.key: q for q in ir.quantities if q.kind != "binding"}
    specific = sorted({q.name for q in formulas.values() if q.basis is not None})
    shared = sum(1 for q in formulas.values() if q.basis is None)
    lines = [
        ir.code,
        f"  bases: {', '.join(ir.bases)}",
        f"  columns: {len(formulas)} ({shared} shared by every basis, "
        f"{len(formulas) - shared} basis-specific); passes: {len(ir.passes)}",
        f"  basis-specific: {', '.join(specific) or '-'}",
    ]
    width = max((len(q.label) for q in formulas.values()), default=0) + 2
    for stage in ir.passes:
        lines += ["", f"pass {stage.index}, {stage.direction}"]
        for key in stage.members:
            quantity = formulas[key]
            lines.append(f"  {quantity.label:<{width}}{quantity.kind:<9}{quantity.owner}")
            lines.append(f"    = {render(quantity.expr)}")
    reached = {group: set[str]() for group in GROUPS}
    for basis in ir.bases:
        manifest = ir.manifest[basis]
        lines += ["", f"reached manifest, {basis}", *_groups(manifest, "  ")]
        for group in GROUPS:
            reached[group] |= getattr(manifest, group)
    declared = bound(ir)
    unreached = Manifest(
        **{group: frozenset(getattr(declared, group) - reached[group]) for group in GROUPS}
    )
    lines += [
        "",
        "declared, read by no formula (validated by avk check: preparation-only inputs,",
        "or inputs of formulas still to come)",
        *_groups(unreached, "  ")[:-1],
    ]
    return "\n".join(lines) + "\n"
