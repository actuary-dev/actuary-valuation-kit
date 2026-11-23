"""Ordered output labels; writers consume this contract without calculations.

An entry is `(output name, source, basis)`. `entries` are value columns: summed in the
aggregate file and present in every per-policy-month row. `keys` lead each per-policy-month
row and are never summed; their source is a column or one of the markers `POLICY` (the
policy number), `STEP` (the projection step, which also leads the aggregate file) and
`CALENDAR` (the calendar month of each step, 1 to 12, from the valuation date).

`seriatim` entries are `(output name, source, basis, step)`: the seriatim file holds one row
per policy, the policy number (the `POLICY` key's name) then each source column's value at its
projection step.

A run with supplied scenarios (not the single deterministic path) leads every file with a
`SCENARIO` column naming each row's scenario.
"""

from dataclasses import dataclass

POLICY = "<policy number>"
STEP = "<projection step>"
CALENDAR = "<calendar month>"
SCENARIO = "Scenario"

type Entry = tuple[str, str, str | None]
type SliceEntry = tuple[str, str, str | None, int]


@dataclass(frozen=True)
class OutputSchema:
    entries: tuple[Entry, ...] = ()
    keys: tuple[Entry, ...] = ()
    # Keys formatted as integers in output files.
    integer_keys: frozenset[str] = frozenset()
    seriatim: tuple[SliceEntry, ...] = ()

    def __post_init__(self) -> None:
        # Projection values share section/alphabetical order across product families.
        # Keys and seriatim slices retain their explicit schema order.
        if any(name.startswith("cashflows_") for name, _, _ in self.entries):

            def section(entry: Entry) -> tuple[int, str]:
                name = entry[0]
                if name.startswith("decrements_"):
                    return (0 if name.endswith("_reserving") else 2, name)
                if name.startswith("cashflows_"):
                    return (1 if name.endswith("_reserving") else 3, name)
                return (4, name)

            object.__setattr__(self, "entries", tuple(sorted(self.entries, key=section)))
        names = [entry[0] for entry in (*self.keys, *self.entries)]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate output name")
        if not self.integer_keys <= {name for name, _, _ in self.keys}:
            raise ValueError("integer_keys must name keys")
        sliced = [entry[0] for entry in self.seriatim]
        if len(set(sliced)) != len(sliced) or self.policy in sliced:
            raise ValueError("Duplicate seriatim output name")
        if any(step < 0 for _, _, _, step in self.seriatim):
            raise ValueError("A seriatim step is a projection step, never negative")

    def insert_after(self, name: str, entries: tuple[Entry, ...]) -> "OutputSchema":
        names = [entry[0] for entry in self.entries]
        if name not in names:
            raise ValueError(f"Unknown output column: {name}")
        i = names.index(name) + 1
        return OutputSchema(
            self.entries[:i] + tuple(entries) + self.entries[i:],
            self.keys,
            self.integer_keys,
            self.seriatim,
        )

    def _key(self, marker: str, what: str) -> str:
        for name, source, _ in self.keys:
            if source == marker:
                return name
        raise ValueError(f"The output schema names no {what} key")

    @property
    def step(self) -> str:
        """The output name of the projection step."""
        return self._key(STEP, "projection step")

    @property
    def policy(self) -> str | None:
        """The output name of the policy number, if the schema has one."""
        try:
            return self._key(POLICY, "policy number")
        except ValueError:
            return None
