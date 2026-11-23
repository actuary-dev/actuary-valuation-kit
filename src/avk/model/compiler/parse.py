"""Read a product class from its source: columns, basis variants, bindings, ports and metadata.

The compiler never calls a formula. Each `(self, t)` method is parsed with `ast`; its single
`return` expression is translated into IR nodes. Expressions must use the supported formula syntax.
"""

import ast
import inspect
import linecache
from abc import ABC
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import FunctionType

from avk.model import lang
from avk.model.ir import (
    BinOp,
    BoolOp,
    Call,
    Compare,
    Const,
    DefinitionError,
    Field,
    Node,
    SourceRef,
    Time,
    UnaryOp,
)

FRAMEWORK = frozenset({object, ABC, lang.Component, lang.Product})
FUNCTIONS = {
    "fma": (3, 3),
    "if_": (3, 3),
    "clip": (3, 3),
    "floor": (1, 1),
    "abs": (1, 1),
    "exp": (1, 1),
    "log": (1, 1),
    "sqrt": (1, 1),
    "min": (2, None),
    "max": (2, None),
}
BINARY: Mapping[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
}
UNARY: Mapping[type[ast.unaryop], str] = {ast.USub: "-", ast.UAdd: "+", ast.Not: "not"}
COMPARE: Mapping[type[ast.cmpop], str] = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
}


@dataclass(frozen=True)
class Ref(Node):
    """Parse-time column reference; `basis` None means the basis being instantiated."""

    name: str
    basis: str | None
    offset: int
    default: Node | None


@dataclass(frozen=True)
class Use(Node):
    """Parse-time binding use, resolved per basis; `index` is None for a bare `self.<name>`."""

    attr: str
    index: tuple[Node, ...] | None
    line: int


@dataclass(frozen=True)
class Method:
    """One `(self, t)` method as written in one class."""

    owner: type
    name: str
    source: SourceRef  # the `def` line; every node line is absolute in this file
    expr: ast.expr | None  # None for an abstract port
    doc: str
    is_override: bool
    on: tuple[str, str] | None
    scope: object
    dims: tuple[object, ...]
    abstract: bool

    def at(self, node: ast.AST) -> SourceRef:
        return SourceRef(self.source.file, getattr(node, "lineno", self.source.line))

    def error(self, node: ast.AST | None, reason: str) -> DefinitionError:
        where = self.source if node is None else self.at(node)
        return DefinitionError(where, self.owner.__name__, self.name, reason)


@dataclass(frozen=True)
class Declared:
    """A binding class attribute as written in one class."""

    owner: type
    name: str
    value: lang.Binding | lang.BasisBinding
    source: SourceRef


@dataclass(frozen=True)
class Requires:
    owner: type
    ports: tuple[str, ...]
    source: SourceRef


@dataclass(frozen=True)
class Composition:
    """Everything the classes of one product declare, most-derived class first."""

    definition: type[lang.Product]
    classes: tuple[type, ...]
    methods: tuple[Method, ...]
    bindings: tuple[Declared, ...]
    requires: tuple[Requires, ...]
    source: SourceRef
    code: str
    bases: tuple[str, ...]
    fields: tuple[str, ...]


Trees = dict[str, ast.Module | None]  # one parse per source file, per `read` call


def _definition[N: (ast.ClassDef, ast.FunctionDef)](
    trees: Trees, item: type | FunctionType, kind: type[N]
) -> tuple[str, N] | None:
    """The `class`/`def` statement of `item`, from its whole file's syntax tree.

    Parsing the whole file (never a dedented excerpt) keeps every line number absolute and
    accepts any layout Python accepts, such as a comment at column 0 inside a method.
    """
    try:
        file = inspect.getsourcefile(item)
        _, start = inspect.getsourcelines(item)
    except (OSError, TypeError):
        return None
    if file is None:
        return None
    if file not in trees:
        text = "".join(linecache.getlines(file))
        try:
            trees[file] = ast.parse(text) if text else None
        except SyntaxError:
            trees[file] = None
    tree = trees[file]
    if tree is None:
        return None
    for node in ast.walk(tree):
        if isinstance(node, kind) and node.name == item.__name__:
            found: N = node
            first = min([found.lineno, *(d.lineno for d in found.decorator_list)])
            if first == start:
                return file, found
    return None


def _class_lines(trees: Trees, cls: type) -> tuple[SourceRef, dict[str, int]]:
    """The class's own line and the line of each top-level assignment in its body."""
    found = _definition(trees, cls, ast.ClassDef)
    if found is None:
        file = inspect.getsourcefile(cls) if isinstance(cls, type) else None
        return SourceRef(file or "<unknown>", getattr(cls, "__firstlineno__", 0)), {}
    file, node = found
    lines: dict[str, int] = {}
    for statement in node.body:
        targets: list[ast.expr] = []
        if isinstance(statement, ast.Assign):
            targets = list(statement.targets)
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        for target in targets:
            names = target.elts if isinstance(target, ast.Tuple) else [target]
            for name in names:
                if isinstance(name, ast.Name):
                    lines.setdefault(name.id, statement.lineno)
    return SourceRef(file, node.lineno), lines


def _method(
    trees: Trees, cls: type, name: str, function: FunctionType, class_source: SourceRef
) -> Method:
    def fail(line: int, reason: str) -> DefinitionError:
        return DefinitionError(SourceRef(class_source.file, line), cls.__name__, name, reason)

    found = _definition(trees, function, ast.FunctionDef)
    if found is None:
        raise fail(class_source.line, "cannot read the formula source of this method")
    file, node = found
    source = SourceRef(file, node.lineno)
    arguments = node.args
    if (
        [argument.arg for argument in arguments.args] != ["self", "t"]
        or arguments.posonlyargs
        or arguments.vararg
        or arguments.kwonlyargs
        or arguments.kwarg
        or arguments.defaults
    ):
        raise fail(source.line, "a column takes exactly (self, t)")
    abstract = bool(getattr(function, "__isabstractmethod__", False))
    body = list(node.body)
    doc = ast.get_docstring(node) or ""
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    expr: ast.expr | None = None
    if not abstract:
        if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
            raise fail(source.line, "a column is a docstring and one `return` expression")
        expr = body[0].value
    on = getattr(function, lang.ON, None)
    dims = getattr(function, lang.DIMS, ())
    return Method(
        cls,
        name,
        source,
        expr,
        doc,
        bool(getattr(function, "__override__", False)),
        on,
        getattr(function, lang.SCOPE, "policy"),
        tuple(dims),
        abstract,
    )


def read(definition: type[lang.Product]) -> Composition:
    classes = tuple(cls for cls in definition.__mro__ if cls not in FRAMEWORK)
    trees: Trees = {}
    product_source, product_lines = _class_lines(trees, definition)

    def meta_error(key: str, kind: str) -> DefinitionError:
        where = SourceRef(product_source.file, product_lines.get(key, product_source.line))
        return DefinitionError(
            where, definition.__name__, key, f"a product declares {key} as {kind}"
        )

    texts: dict[str, str] = {}
    for key in ("CODE", "LABEL"):
        value = getattr(definition, key, None)
        if not isinstance(value, str) or not value:
            raise meta_error(key, "a nonempty string")
        texts[key] = value
    names: dict[str, tuple[str, ...]] = {}
    for key in ("BASES", "FIELDS"):
        value = getattr(definition, key, None)
        if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
            raise meta_error(key, "a tuple of strings")
        names[key] = value
    if not names["BASES"] or len(set(names["BASES"])) != len(names["BASES"]):
        raise meta_error("BASES", "a nonempty tuple of distinct basis names")
    methods: list[Method] = []
    bindings: list[Declared] = []
    requires: list[Requires] = []
    for cls in classes:
        class_source, lines = (
            _class_lines(trees, cls) if cls is not definition else (product_source, product_lines)
        )
        for name, value in vars(cls).items():
            if name.startswith("__") and name.endswith("__"):
                continue
            where = SourceRef(class_source.file, lines.get(name, class_source.line))
            if isinstance(value, FunctionType):
                methods.append(_method(trees, cls, name, value, class_source))
            elif isinstance(value, lang.Binding | lang.BasisBinding):
                bindings.append(Declared(cls, name, value, where))
            elif name == "REQUIRES":
                if not isinstance(value, tuple) or not all(isinstance(p, str) for p in value):
                    raise DefinitionError(
                        where, cls.__name__, name, "REQUIRES is a tuple of column names"
                    )
                requires.append(Requires(cls, value, where))
    return Composition(
        definition,
        classes,
        tuple(methods),
        tuple(bindings),
        tuple(requires),
        product_source,
        texts["CODE"],
        names["BASES"],
        names["FIELDS"],
    )


@dataclass(frozen=True)
class Names:
    """What a formula may read: the composition's columns, variants, bindings and fields."""

    columns: frozenset[str]
    variants: frozenset[str]  # method names of `@on` variants
    bindings: frozenset[str]
    fields: frozenset[str]
    bases: tuple[str, ...]
    readable: Mapping[type, frozenset[str]]  # per component: columns it defines or requires
    product: str


def translate(method: Method, names: Names) -> Node:
    """The method's return expression as IR nodes, with column and binding uses unresolved."""
    assert method.expr is not None
    readable = names.readable.get(method.owner)

    def column(name: str, node: ast.AST) -> str:
        if name in names.columns:
            if readable is not None and name not in readable:
                raise method.error(
                    node,
                    f"reads column '{name}', which {method.owner.__name__} neither defines "
                    "nor lists in REQUIRES",
                )
            return name
        if name in names.variants:
            raise method.error(node, f"'{name}' is a basis variant (@on), not a column")
        if name in names.bindings:
            raise method.error(node, f"binding '{name}' is read as self.{name}, not called")
        raise method.error(
            node, f"unknown name '{name}': no column or binding of {names.product} has that name"
        )

    def reference(node: ast.expr) -> tuple[str, str | None]:
        """`self.col` or `at_basis("basis", self.col)`: a column without its month."""
        if _is_self_attribute(node):
            assert isinstance(node, ast.Attribute)
            return column(node.attr, node), None
        if isinstance(node, ast.Call) and _named(node.func, "at_basis"):
            if node.keywords or len(node.args) != 2:
                raise method.error(node, "at_basis takes (basis, self.column)")
            basis_node, target = node.args
            if not isinstance(basis_node, ast.Constant) or not isinstance(basis_node.value, str):
                raise method.error(node, "at_basis names its basis as a string")
            if basis_node.value not in names.bases:
                raise method.error(
                    node,
                    f"basis '{basis_node.value}' is not in the basis set {names.bases}",
                )
            if not _is_self_attribute(target):
                raise method.error(node, "at_basis takes a column reference, self.column")
            assert isinstance(target, ast.Attribute)
            return column(target.attr, target), basis_node.value
        raise method.error(node, "expected a column reference: self.column or at_basis(...)")

    def visit(node: ast.expr) -> Node:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int | float):
                raise method.error(node, f"unsupported constant {node.value!r}: numbers only")
            return Const(float(node.value))
        if isinstance(node, ast.Name):
            if node.id == "t":
                return Time()
            raise method.error(
                node, f"unknown name '{node.id}': read columns and bindings through self."
            )
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Attribute)
                and _is_self_attribute(node.value)
                and node.value.attr == "policy"
            ):
                if node.attr not in names.fields:
                    raise method.error(
                        node, f"unknown model-point field '{node.attr}': not in FIELDS"
                    )
                return Field(node.attr)
            if _is_self_attribute(node):
                if node.attr in names.bindings:
                    return Use(node.attr, None, method.at(node).line)
                if node.attr in names.columns:
                    raise method.error(
                        node, f"column '{node.attr}' is read as self.{node.attr}(t) or via prev/nxt"
                    )
                column(node.attr, node)
            raise method.error(
                node, "unsupported attribute: use self.<name> or self.policy.<field>"
            )
        if isinstance(node, ast.Subscript):
            if not _is_self_attribute(node.value):
                raise method.error(node, "only bindings are indexed: self.<binding>[...]")
            assert isinstance(node.value, ast.Attribute)
            attr = node.value.attr
            if attr not in names.bindings:
                if attr in names.columns:
                    raise method.error(node, f"column '{attr}' is not indexed; call it with (t)")
                column(attr, node)
            items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            if any(isinstance(item, ast.Slice) for item in items):
                raise method.error(node, "slices are not supported")
            return Use(attr, tuple(visit(item) for item in items), method.at(node).line)
        if isinstance(node, ast.Call):
            return call(node)
        if isinstance(node, ast.BinOp):
            op = BINARY.get(type(node.op))
            if op is None:
                raise method.error(node, f"unsupported operator {type(node.op).__name__}")
            return BinOp(op, visit(node.left), visit(node.right))  # type: ignore[arg-type]
        if isinstance(node, ast.UnaryOp):
            op = UNARY.get(type(node.op))
            if op is None:
                raise method.error(node, f"unsupported operator {type(node.op).__name__}")
            return UnaryOp(op, visit(node.operand))  # type: ignore[arg-type]
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise method.error(node, "chained comparison: write a < b and b < c")
            op = COMPARE.get(type(node.ops[0]))
            if op is None:
                raise method.error(node, f"unsupported comparison {type(node.ops[0]).__name__}")
            return Compare(op, visit(node.left), visit(node.comparators[0]))  # type: ignore[arg-type]
        if isinstance(node, ast.BoolOp):
            values = tuple(visit(value) for value in node.values)
            return BoolOp("and" if isinstance(node.op, ast.And) else "or", values)
        if isinstance(node, ast.IfExp):
            raise method.error(node, "use if_(condition, then, otherwise), not `a if c else b`")
        raise method.error(
            node, f"unsupported construct {type(node).__name__} (master plan §4.6 only)"
        )

    def call(node: ast.Call) -> Node:
        if node.keywords:
            raise method.error(node, "keyword arguments are not supported in formulas")
        if isinstance(node.func, ast.Call) and _named(node.func.func, "at_basis"):
            _at_month_t(node)
            name, basis = reference(node.func)
            return Ref(name, basis, 0, None)
        if _is_self_attribute(node.func):
            assert isinstance(node.func, ast.Attribute)
            name = column(node.func.attr, node.func)
            _at_month_t(node)
            return Ref(name, None, 0, None)
        if isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn in ("prev", "nxt"):
                if len(node.args) != 2:
                    raise method.error(node, f"{fn} takes (self.column, default)")
                name, basis = reference(node.args[0])
                return Ref(name, basis, -1 if fn == "prev" else 1, visit(node.args[1]))
            if fn == "at_basis":
                raise method.error(
                    node, "at_basis(...) is a column reference: call it with (t) or use prev/nxt"
                )
            if fn in FUNCTIONS:
                low, high = FUNCTIONS[fn]
                if len(node.args) < low or (high is not None and len(node.args) > high):
                    expected = f"{low}" if low == high else f"at least {low}"
                    raise method.error(node, f"{fn} takes {expected} arguments")
                return Call(fn, tuple(visit(arg) for arg in node.args))  # type: ignore[arg-type]
            raise method.error(node, f"unknown function '{fn}' (master plan §4.6 only)")
        raise method.error(node, "unsupported call")

    def _at_month_t(node: ast.Call) -> None:
        if len(node.args) != 1 or not (
            isinstance(node.args[0], ast.Name) and node.args[0].id == "t"
        ):
            raise method.error(
                node, "a column is read at the same month as (t); use prev()/nxt() otherwise"
            )

    return visit(method.expr)


def _is_self_attribute(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _named(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def owners(methods: Sequence[Method], name: str) -> list[Method]:
    """Concrete, non-variant definitions of column `name`, most-derived class first."""
    return [m for m in methods if m.name == name and not m.abstract and m.on is None]
