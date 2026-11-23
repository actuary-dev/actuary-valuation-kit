"""Scheduling: strongly connected components into forward and backward passes.

Columns that read each other across months form a
component that shares one pass whose direction matches its time offsets. A same-month cycle,
or a component needing both `prev` and `nxt`, is rejected: a future same-month solve is an
explicit solve region. Ordinary dependency cycles are rejected.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from avk.model.ir import DefinitionError, Pass, Quantity

Key = tuple[str, str | None]


@dataclass(frozen=True)
class Schedule:
    passes: tuple[Pass, ...]
    states: frozenset[Key]  # columns carried between months inside their own recursion


def components(nodes: Sequence[Key], edges: Mapping[Key, Sequence[Key]]) -> list[list[Key]]:
    """Tarjan's strongly connected components, iteratively; dependencies come first."""
    index: dict[Key, int] = {}
    low: dict[Key, int] = {}
    stack: list[Key] = []
    on_stack: set[Key] = set()
    found: list[list[Key]] = []
    for root in nodes:
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(edges[root]))]
        while work:
            node, pending = work[-1]
            for target in pending:
                if target not in index:
                    index[target] = low[target] = len(index)
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, iter(edges[target])))
                    break
                if target in on_stack:
                    low[node] = min(low[node], index[target])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component: list[Key] = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    found.append(component)
    return found


def _ordered(members: Iterable[Key], position: Mapping[Key, int]) -> list[Key]:
    return sorted(members, key=position.__getitem__)


def _ready(offset: int, other: int, k: int) -> bool:
    """Is a dependency computed in pass `other` readable from pass `k` at this offset?"""
    if offset == 0:
        return other <= k
    if offset == -1:  # last month: an earlier pass, or this pass running forward
        return other < k or (other == k and k % 2 == 0)
    return other < k or (other == k and k % 2 == 1)  # next month: this pass running backward


def _first_pass(direction: int, external: Sequence[tuple[int, int]]) -> int:
    """The first pass (even: forward, odd: backward) matching the component's own direction
    (-1 reads `prev`, +1 reads `nxt`) where every external dependency is ready."""
    k = 0
    while True:
        aligned = not direction or (direction == -1) == (k % 2 == 0)
        if aligned and all(_ready(offset, other, k) for offset, other in external):
            return k
        k += 1


def schedule(quantities: Sequence[Quantity]) -> Schedule:
    formulas = [q for q in quantities if q.kind != "binding"]
    by_key = {q.key: q for q in formulas}
    position = {q.key: i for i, q in enumerate(formulas)}
    nodes = [q.key for q in formulas]
    offsets: dict[Key, list[tuple[Key, int]]] = {
        q.key: [((d.name, d.basis), d.offset) for d in q.deps] for q in formulas
    }
    edges = {
        key: _ordered({target for target, _ in deps}, position) for key, deps in offsets.items()
    }

    def fail(members: Iterable[Key], reason: str) -> DefinitionError:
        involved = sorted(
            (by_key[key] for key in members), key=lambda q: (q.source.file, q.source.line, q.label)
        )
        first = involved[0]
        labels = ", ".join(q.label for q in involved)
        return DefinitionError(first.source, first.owner, first.label, reason.format(labels))

    pass_of: dict[Key, int] = {}
    order: list[tuple[int, list[Key]]] = []
    states: set[Key] = set()
    for component in components(nodes, edges):
        members = set(component)
        inner = [
            (key, target, offset)
            for key in component
            for target, offset in offsets[key]
            if target in members
        ]
        same_month = {key: [t for k, t, o in inner if k == key and o == 0] for key in component}
        for cycle in components(_ordered(component, position), same_month):
            if len(cycle) > 1 or cycle[0] in same_month[cycle[0]]:
                raise fail(cycle, "same-month cycle through {}: no evaluation order exists")
        directions = {offset for _, _, offset in inner if offset}
        if directions == {-1, 1}:
            raise fail(
                component,
                "the cycle {} needs both prev() and nxt(); a recursion runs in one direction "
                "(write basis differences as @on, not run-time flags)",
            )
        states.update(target for _, target, offset in inner if offset)
        direction = -1 if -1 in directions else 1 if 1 in directions else 0
        external = [
            (offset, pass_of[target])
            for key in component
            for target, offset in offsets[key]
            if target not in members
        ]
        k = _first_pass(direction, external)
        for key in component:
            pass_of[key] = k
        # Inside a component, same-month dependencies first (the offset-0 graph is acyclic).
        ready: list[Key] = []
        remaining = _ordered(component, position)
        while remaining:
            for key in remaining:
                if all(t in ready for t in same_month[key]):
                    ready.append(key)
                    remaining.remove(key)
                    break
        order.append((k, ready))

    used = sorted(set(pass_of.values()))
    passes = tuple(
        Pass(
            index,
            "forward" if k % 2 == 0 else "backward",
            tuple(key for pass_k, keys in order if pass_k == k for key in keys),
        )
        for index, k in enumerate(used)
    )
    return Schedule(passes, frozenset(states))
