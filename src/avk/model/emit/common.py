"""Device-independent code generation: the kernel layout and formulas as plain scalar Python.

The emitted text is the subset every target accepts (Numba CPU, CUDA device functions, pure
Python): loops, `if`, arithmetic, `math` and indexing on float64 values. Nothing from the
definition layer enters it; names, strings and rules are resolved here, at generation time.

The helpers in `HELPERS` implement IEEE floating-point behaviour in compiled and
interpreted execution:
- `/` is IEEE division; `//` and `%` floor like NumPy; `**` gives NaN for a negative base to a
  fractional power; `max`/`min`/`clip` propagate NaN;
- comparisons and `and`/`or`/`not` give 1.0 or 0.0, with NaN treated as true;
- `if_` selects one branch's value; the other cannot leak into the result.
"""

from dataclasses import dataclass
from types import MappingProxyType

from avk.model.ir import (
    BinOp,
    BoolOp,
    Bound,
    Call,
    Col,
    Compare,
    Const,
    DefinitionError,
    Field,
    Lookup,
    Node,
    Param,
    Pass,
    ProductIR,
    Quantity,
    RunParam,
    Time,
    UnaryOp,
    walk,
)
from avk.model.lang import AxisRule

# Policies per logical reduction block: fixes the summation order of every aggregate.
BLOCK = 1024

HELPERS = """
def _div(a, b):
    if b == 0.0:
        if a != a or a == 0.0:
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def _mod(a, b):
    # Python's float % is NumPy's npy_divmod remainder; only its raising cases are guarded.
    if b == 0.0 or a != a or b != b or a == math.inf or a == -math.inf:
        return math.nan
    return a % b


def _fdiv(a, b):
    # Python's float // is NumPy's npy_divmod quotient; only its raising cases are guarded.
    if b == 0.0 or a != a or b != b or a == math.inf or a == -math.inf:
        return _div(a, b)
    return a // b


def _pow(a, b):
    if a < 0.0 and b == b and b % 1.0 != 0.0 and b != math.inf and b != -math.inf:
        return math.nan
    if a == 0.0 and b < 0.0:
        if b % 2.0 == 1.0:
            return math.copysign(math.inf, a)
        return math.inf
    if a == a and b == b and a != 0.0 and abs(a) != math.inf and abs(b) != math.inf:
        # Python's ** raises OverflowError where NumPy gives inf: square a half power instead,
        # since float multiplication overflows silently (compiled code takes the same path).
        e = b * math.log(abs(a))
        if e > 709.0:
            sign = -1.0 if a < 0.0 and b % 2.0 == 1.0 else 1.0
            if e > 1400.0:
                return sign * math.inf
            h = abs(a) ** (0.5 * b)
            return sign * (h * h)
    return a ** b


def _floor(x):
    if x != x or x >= 4503599627370496.0 or x <= -4503599627370496.0:
        return x
    return float(math.floor(x))


def _max(a, b):
    if a != a:
        return a
    if b != b:
        return b
    return a if a >= b else b


def _min(a, b):
    if a != a:
        return a
    if b != b:
        return b
    return a if a <= b else b


def _exp(x):
    if x > 709.782712893384:
        return math.inf
    return math.exp(x)


def _log(x):
    if x != x or x == math.inf:
        return x
    if x < 0.0:
        return math.nan
    if x == 0.0:
        return -math.inf
    return math.log(x)


def _sqrt(x):
    if x != x or x == math.inf:
        return x
    if x < 0.0:
        return math.nan
    return math.sqrt(x)


def _clamp(v, start, n):
    if v != v or v <= start:
        return 0
    if v >= start + n - 1:
        return n - 1
    return int(math.floor(v)) - start
"""
HELPER_NAMES = (
    "_div",
    "_mod",
    "_fdiv",
    "_pow",
    "_floor",
    "_max",
    "_min",
    "_exp",
    "_log",
    "_sqrt",
    "_clamp",
)


@dataclass(frozen=True)
class Layout:
    """Where everything a kernel reads and writes sits in its packed arguments.

    `columns` are the scratch rows (labels `name` or `name@basis`): first the `independent`
    columns, which no scenario variable reaches (one row of `oi (NI, M)` each, computed once
    per policy), then the scenario-dependent ones (one row of `od (ND, M, tile)` each,
    computed for every scenario of a tile), each group in evaluation order. `tables` carry
    their binding's axis rules; `keymaps` and `starts` list (table, axis) for keymap and
    integer axes; `params` is (basis, name) grouped by basis in `bases` order; `run_params`
    are the run parameters by name, packed after the product parameters; `curves` are the
    monthly schedules (name, out-of-range rule), one 1-D argument each after the tables.
    """

    bases: tuple[str, ...]
    columns: tuple[str, ...]
    keys: tuple[tuple[str, str | None], ...]
    fields: tuple[str, ...]
    tables: tuple[tuple[str, tuple[AxisRule, ...]], ...]
    keymaps: tuple[tuple[str, int], ...]
    starts: tuple[tuple[str, int], ...]
    params: tuple[tuple[str, str], ...]
    scen_vars: tuple[str, ...]
    independent: int
    run_params: tuple[str, ...] = ()
    curves: tuple[tuple[str, AxisRule], ...] = ()
    monthly_params: tuple[str, ...] = ()

    @classmethod
    def of(cls, ir: ProductIR) -> "Layout":
        quantities = {q.key: q for q in ir.quantities}
        ordered = tuple(key for stage in ir.passes for key in stage.members)
        dependent = scenario_dependent(ir)
        keys = tuple(k for k in ordered if k not in dependent)
        keys += tuple(k for k in ordered if k in dependent)
        rules: dict[str, tuple[AxisRule, ...]] = {}
        for quantity in ir.quantities:
            if isinstance(quantity.expr, Bound) and (
                quantity.expr.kind in ("tables", "curves")
                or (quantity.expr.kind == "run_params" and quantity.expr.axes)
            ):
                rules[quantity.expr.name] = quantity.expr.axes
        tables = sorted(set().union(*(m.tables for m in ir.manifest.values())))
        curves = sorted(set().union(*(m.curves for m in ir.manifest.values())))
        run_params = set().union(*(m.run_params for m in ir.manifest.values()))
        monthly = run_params & {
            quantity.expr.name
            for quantity in ir.quantities
            if isinstance(quantity.expr, Bound)
            and quantity.expr.kind == "run_params"
            and quantity.expr.axes
        }
        curves = sorted(set(curves) | monthly)
        return cls(
            bases=ir.bases,
            columns=tuple(quantities[key].label for key in keys),
            keys=keys,
            fields=tuple(sorted(set().union(*(m.fields for m in ir.manifest.values())))),
            tables=tuple((name, rules[name]) for name in tables),
            keymaps=tuple(
                (name, axis)
                for name in tables
                for axis, rule in enumerate(rules[name])
                if rule.kind == "keymap"
            ),
            starts=tuple(
                (name, axis)
                for name in tables
                for axis, rule in enumerate(rules[name])
                if rule.kind == "int"
            ),
            params=tuple(
                (basis, name) for basis in ir.bases for name in sorted(ir.manifest[basis].params)
            ),
            scen_vars=tuple(sorted(set().union(*(m.scen_vars for m in ir.manifest.values())))),
            independent=len(keys) - len(dependent),
            run_params=tuple(sorted(run_params - monthly)),
            curves=tuple((name, rules[name][0]) for name in curves),
            monthly_params=tuple(sorted(monthly)),
        )

    def row(self, label: str) -> int:
        return self.columns.index(label)


def scenario_dependent(ir: ProductIR) -> frozenset[tuple[str, str | None]]:
    """The formulas a scenario variable reaches, directly or through any dependency."""
    formulas = {q.key: q.expr for q in ir.quantities if q.kind != "binding"}
    reads = {
        key: {(n.name, n.basis) for n in walk(expr) if isinstance(n, Col)}
        for key, expr in formulas.items()
    }
    found = {
        key
        for key, expr in formulas.items()
        if any(isinstance(n, Lookup) and n.kind == "scen_vars" for n in walk(expr))
    }
    grown = True
    while grown:
        more = {key for key, read in reads.items() if key not in found and read & found}
        found |= more
        grown = bool(more)
    return frozenset(found)


class Stage:
    """Translates one part of a pass into statements over locals and the scratch arrays.

    `part` is "i" (the pass's scenario-independent members, read and written as `oi[row, t]`)
    or "d" (its scenario-dependent members, `od[row - NI, t, u]` for scenario `s = s0 + u`).
    A backward pass runs its months downward, so a member's `nxt` reads the row already
    written at `t + 1`.
    """

    def __init__(self, ir: ProductIR, layout: Layout, stage: Pass, part: str) -> None:
        self.layout = layout
        self.stage = stage
        self.part = part
        self.quantities = MappingProxyType({q.key: q for q in ir.quantities})
        self.rows = {key: row for row, key in enumerate(layout.keys)}
        self.members = tuple(
            key for key in stage.members if (self.rows[key] >= layout.independent) == (part == "d")
        )
        self.tables = {name: index for index, (name, _) in enumerate(layout.tables)}
        self.rules = dict(layout.tables)
        self.done: set[tuple[str, str | None]] = set()
        self.lines: list[str] = []
        self.temp = 0
        self.quantity: Quantity | None = None

    def cell(self, row: int, month: str) -> str:
        if row < self.layout.independent:
            return f"oi[{row}, {month}]"
        return f"od[{row - self.layout.independent}, {month}, u]"

    def fail(self, reason: str) -> DefinitionError:
        assert self.quantity is not None
        return DefinitionError(
            self.quantity.source, self.quantity.owner, self.quantity.label, reason
        )

    def fresh(self, prefix: str) -> str:
        self.temp += 1
        return f"{prefix}{self.temp}"

    def body(self) -> list[str]:
        """The statements evaluating this part's members at month `t`, in order."""
        for key in self.members:
            self.quantity = self.quantities[key]
            value = self.expr(self.quantity.expr)
            row = self.rows[key]
            self.lines.append(f"c{row} = {value}")
            self.lines.append(f"{self.cell(row, 't')} = c{row}")
            self.done.add(key)
        return self.lines

    def expr(self, node: Node) -> str:
        if isinstance(node, Const):
            return _number(node.value)
        if isinstance(node, Time):
            return "tf"
        if isinstance(node, Field):
            return f"f{self.layout.fields.index(node.name)}"
        if isinstance(node, Param):
            assert self.quantity is not None
            basis = self.quantity.basis or self.layout.bases[0]
            return f"p{self.layout.params.index((basis, node.name))}"
        if isinstance(node, RunParam):
            return f"p{len(self.layout.params) + self.layout.run_params.index(node.name)}"
        if isinstance(node, Col):
            return self.column(node)
        if isinstance(node, Lookup):
            return self.lookup(node)
        if isinstance(node, BinOp):
            left, right = self.expr(node.left), self.expr(node.right)
            if node.op in ("+", "-", "*"):
                return f"({left} {node.op} {right})"
            helper = {"/": "_div", "//": "_fdiv", "%": "_mod", "**": "_pow"}[node.op]
            return f"{helper}({left}, {right})"
        if isinstance(node, UnaryOp):
            operand = self.expr(node.operand)
            if node.op == "not":
                return f"(1.0 if {operand} == 0.0 else 0.0)"
            return f"({node.op}{operand})"
        if isinstance(node, Compare):
            left, right = self.expr(node.left), self.expr(node.right)
            return f"(1.0 if {left} {node.op} {right} else 0.0)"
        if isinstance(node, BoolOp):
            tests = f" {node.op} ".join(f"{self.expr(value)} != 0.0" for value in node.values)
            return f"(1.0 if ({tests}) else 0.0)"
        if isinstance(node, Call):
            return self.call(node)
        raise self.fail(f"cannot emit {type(node).__name__}")

    def column(self, node: Col) -> str:
        key = (node.name, node.basis)
        row = self.rows[key]
        if node.offset == 0:
            return f"c{row}" if key in self.done else self.cell(row, "t")
        if node.default is None:
            raise self.fail(f"'{node.name}' is read at another month without a default")
        default = self.expr(node.default)
        if node.offset == -1:
            if key in self.stage.members and self.stage.direction == "backward":
                raise self.fail("a backward pass cannot read its own previous month")
            return f"({self.cell(row, 't - 1')} if t > 0 else {default})"
        if key in self.stage.members and self.stage.direction == "forward":
            raise self.fail("a forward pass cannot read its own next month")
        return f"({self.cell(row, 't + 1')} if t + 1 < M else {default})"

    def lookup(self, node: Lookup) -> str:
        if node.kind in ("curves", "run_params"):
            slot = [name for name, _ in self.layout.curves].index(node.name)
            if node.kind == "run_params" and isinstance(node.index[0], Time):
                # Preparation/packing proves a value for every projection month.
                return f"cv{slot}[t]"
            rule = self.layout.curves[slot][1]
            value = self.expr(node.index[0])
            if not value.isidentifier():  # evaluated once, read by the index and its rules
                name = self.fresh("x")
                self.lines.append(f"{name} = {value}")
                value = name
            size = f"cv{slot}.shape[0]"
            read = f"cv{slot}[_clamp({value}, 0, {size})]"
            inside = []
            if rule.below == "zero_rows":
                inside.append(f"{value} >= 0.0")
            if rule.above == "zero":
                inside.append(f"{value} < {size}")
            if not inside:
                return read
            return f"({read} if ({' and '.join(inside)}) else 0.0)"
        if node.kind == "scen_vars":
            month = self.expr(node.index[0])
            slot = self.layout.scen_vars.index(node.name)
            return f"scn[{slot}, s0 + u, _clamp({month}, 0, M)]"
        table = self.tables[node.name]
        indices, inside = [], []
        for axis, (rule, index) in enumerate(zip(self.rules[node.name], node.index, strict=True)):
            if rule.kind == "keymap":
                slot = self.layout.keymaps.index((node.name, axis))
                if rule.above == "zero":
                    inside.append(f"k{slot} >= 0")
                    indices.append(f"max(k{slot}, 0)")
                else:
                    indices.append(f"k{slot}")
                continue
            value = self.expr(index)
            if not value.isidentifier():  # evaluated once, read by the index and its rule
                name = self.fresh("x")
                self.lines.append(f"{name} = {value}")
                value = name
            start = f"ist[{self.layout.starts.index((node.name, axis))}]"
            size = f"tb{table}.shape[{axis}]"
            indices.append(f"_clamp({value}, {start}, {size})")
            # 'error' rules are proven by preparation; the clamp is the memory-safety net.
            if rule.below == "zero_rows":
                inside.append(f"{value} >= {start}")
            if rule.above == "zero":
                inside.append(f"{value} < {start} + {size}")
        read = f"tb{table}[{', '.join(indices)}]"
        if not inside:
            return read
        return f"({read} if ({' and '.join(inside)}) else 0.0)"

    def call(self, node: Call) -> str:
        args = [self.expr(arg) for arg in node.args]
        if node.fn == "fma":
            return f"math.fma({', '.join(args)})"
        if node.fn == "if_":
            return f"({args[1]} if {args[0]} != 0.0 else {args[2]})"
        if node.fn == "clip":
            return f"_min(_max({args[0]}, {args[1]}), {args[2]})"
        if node.fn in ("min", "max"):
            result = args[0]
            for arg in args[1:]:
                result = f"_{node.fn}({result}, {arg})"
            return result
        if node.fn == "abs":
            return f"abs({args[0]})"
        return f"_{node.fn}({args[0]})"


def _number(value: float) -> str:
    value = float(value)
    if value != value:
        return "math.nan"
    if value in (float("inf"), float("-inf")):
        return "math.inf" if value > 0 else "(-math.inf)"
    text = repr(value)
    return f"({text})" if value < 0 or text.startswith("-") else text
