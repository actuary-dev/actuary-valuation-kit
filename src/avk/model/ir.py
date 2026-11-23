"""The compiler's intermediate representation: frozen, scalar, free of definition objects.

A `ProductIR` is what the front end (`model.compiler`) proves about a product: every column
once per basis (or once, shared, when its lowered formula is identical on every basis), its
dependencies with time offsets, the passes that evaluate them and each basis's reached
manifest. Expressions are trees of the frozen nodes below; nothing else enters them.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Literal

from avk.model.lang import AxisRule
from avk.model.manifest import Manifest

_PACKAGE = Path(__file__).resolve().parents[1]


def display_path(file: str) -> str:
    """Package files as `avk/...`, so messages and explanations are machine independent."""
    try:
        return "avk/" + Path(file).resolve().relative_to(_PACKAGE).as_posix()
    except ValueError:
        return file


@dataclass(frozen=True)
class SourceRef:
    file: str
    line: int

    def __str__(self) -> str:
        return f"{display_path(self.file)}:{self.line}"


class DefinitionError(ValueError):
    """A product definition the compiler rejects: `<file>:<line>: <owner>.<member>: <reason>`.

    The run layer re-raises it as `FormulaError` (the numerical core imports no other package).
    """

    def __init__(self, source: SourceRef, owner: str, member: str, reason: str) -> None:
        super().__init__(f"{source}: {owner}.{member}: {reason}")
        self.source = source
        self.owner = owner
        self.member = member
        self.reason = reason


class Node:
    """An expression node. Subclasses are frozen dataclasses whose children are nodes."""


@dataclass(frozen=True)
class Const(Node):
    value: float


@dataclass(frozen=True)
class Time(Node):
    """The projection month `t` (0 is the valuation instant)."""


@dataclass(frozen=True)
class Field(Node):
    """A model-point field: `self.policy.<name>`."""

    name: str


@dataclass(frozen=True)
class Param(Node):
    """A scalar product parameter, by its source name."""

    name: str


@dataclass(frozen=True)
class RunParam(Node):
    """A scalar run parameter, set by the run type ()."""

    name: str


@dataclass(frozen=True)
class Lookup(Node):
    """A table, scenario-variable or curve value at integer indices."""

    kind: Literal["tables", "scen_vars", "curves", "run_params"]
    name: str
    index: tuple[Node, ...]


@dataclass(frozen=True)
class Col(Node):
    """Column `name` on `basis` (None: shared by every basis) at `t + offset`.

    `offset` is -1 (`prev`), 0 or +1 (`nxt`); `default` applies outside the horizon.
    """

    name: str
    basis: str | None
    offset: int = 0
    default: Node | None = None


@dataclass(frozen=True)
class BinOp(Node):
    op: Literal["+", "-", "*", "/", "//", "%", "**"]
    left: Node
    right: Node


@dataclass(frozen=True)
class UnaryOp(Node):
    op: Literal["-", "+", "not"]
    operand: Node


@dataclass(frozen=True)
class Compare(Node):
    """A comparison: 1.0 when true, 0.0 when false."""

    op: Literal["<", "<=", ">", ">=", "==", "!="]
    left: Node
    right: Node


@dataclass(frozen=True)
class BoolOp(Node):
    op: Literal["and", "or"]
    values: tuple[Node, ...]


@dataclass(frozen=True)
class Call(Node):
    fn: Literal["if_", "clip", "floor", "min", "max", "abs", "exp", "log", "sqrt", "fma"]
    args: tuple[Node, ...]


@dataclass(frozen=True)
class Bound(Node):
    """The declaration behind a binding quantity (never inside a formula)."""

    kind: Literal["tables", "params", "run_params", "scen_vars", "curves"]
    name: str
    value: str | None
    axes: tuple[AxisRule, ...]


def children(node: Node) -> Iterator[Node]:
    for item in fields(node):  # type: ignore[arg-type]
        value = getattr(node, item.name)
        if isinstance(value, Node):
            yield value
        elif isinstance(value, tuple):
            yield from (child for child in value if isinstance(child, Node))


def walk(node: Node) -> Iterator[Node]:
    yield node
    for child in children(node):
        yield from walk(child)


def transform(node: Node, change: Callable[[Node], Node]) -> Node:
    """Rebuild `node` bottom-up, applying `change` to every rebuilt node."""
    updates: dict[str, object] = {}
    for item in fields(node):  # type: ignore[arg-type]
        value = getattr(node, item.name)
        if isinstance(value, Node):
            updates[item.name] = transform(value, change)
        elif isinstance(value, tuple) and any(isinstance(child, Node) for child in value):
            updates[item.name] = tuple(
                transform(child, change) if isinstance(child, Node) else child for child in value
            )
    return change(replace(node, **updates) if updates else node)  # type: ignore[type-var]


@dataclass(frozen=True)
class Dep:
    name: str
    basis: str | None
    offset: int


@dataclass(frozen=True)
class Quantity:
    name: str
    basis: str | None
    owner: str
    expr: Node
    deps: tuple[Dep, ...]
    scope: Literal["policy"]
    dims: tuple[str, ...]
    kind: Literal["formula", "state", "binding"]
    source: SourceRef
    doc: str

    @property
    def key(self) -> tuple[str, str | None]:
        return self.name, self.basis

    @property
    def label(self) -> str:
        return self.name if self.basis is None else f"{self.name}@{self.basis}"


@dataclass(frozen=True)
class Pass:
    """One stage: its members are evaluated in order at every month, forward or backward."""

    index: int
    direction: Literal["forward", "backward"]
    members: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class ProductIR:
    code: str
    bases: tuple[str, ...]
    quantities: tuple[Quantity, ...]
    passes: tuple[Pass, ...]
    manifest: Mapping[str, Manifest]
