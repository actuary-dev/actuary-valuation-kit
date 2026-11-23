"""Strict named cases, their runtime parameters and valuation-date impact values.

Mortality, morbidity, lapse, expense and inflation shocks reach the one compiled composition
only as run parameters (`case_parameters`): a whole-run shock is a window over every month,
so both share one formula. Interest is the one shock applied to inputs, because it changes
the generated economic scenarios (`case_report`).
"""

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt
import polars as pl

from avk.assumptions.models import InterestCurveAssumption
from avk.esg.deterministic import DeterministicCurveESG
from avk.runs.numbers import finite_number
from avk.runtime.errors import ConfigError, reader_failure
from avk.runtime.progress import fingerprint, generated_file

if TYPE_CHECKING:
    from avk.runs.check import CheckReport
    from avk.runs.config import RunConfig

SHOCK_NAMES = ("mortality", "morbidity", "lapse", "expense", "inflation", "interest")
RATE_SHOCKS = ("mortality", "morbidity", "lapse", "expense")  # monthly add/mult schedules


@dataclass(frozen=True)
class Shock:
    additive: float
    multiplicative: float
    start: int | None = None
    end: int | None = None
    maximum_decrease: float = 1.0
    windows: tuple["Shock", ...] = ()


@dataclass(frozen=True)
class Case:
    name: str
    shocks: dict[str, Shock]
    mass_lapse: float = 0.0
    overrides: dict[str, Any] = field(default_factory=dict)


def _span(shock: Shock, months: int) -> slice:
    """The projection months a shock covers: its window, else every month."""
    if shock.start is None:
        return slice(0, months)
    assert shock.end is not None
    return slice(shock.start, shock.end + 1)


def _inflation_months(shock: Shock | None, months: int) -> npt.NDArray[np.float64]:
    """Months of growth at the shocked inflation rate up to each projection month.

    Expenses grow from month 1, so growth into month m (m >= 2) happens in month m. A window
    counts its months, then holds the count: the higher price level persists after it. A
    whole-run shock grows every month (`t - 1`, as the unshocked escalation does).
    """
    month = np.arange(months, dtype=np.float64)
    if shock is None:
        return np.zeros(months)
    if shock.start is None:
        return month - 1.0
    assert shock.end is not None
    first = max(shock.start, 2)
    return np.clip(month - first + 1, 0.0, max(shock.end - first + 1, 0))


def case_parameters(case: Case | None, months: int) -> dict[str, float | npt.NDArray[np.float64]]:
    """The run parameters one case sets (the base, None, sets the neutral ones)."""
    shocks = case.shocks if case is not None else {}
    lapse_cap = np.ones(months)
    parameters: dict[str, float | npt.NDArray[np.float64]] = {
        "case_mass_lapse": case.mass_lapse if case is not None else 0.0,
        "lapse_maximum_decrease": lapse_cap,
    }
    for name in RATE_SHOCKS:
        addition, multiplier = np.zeros(months), np.ones(months)
        shock = shocks.get(name)
        for window in (shock.windows or (shock,)) if shock is not None else ():
            addition[_span(window, months)] = window.additive
            multiplier[_span(window, months)] = window.multiplicative
            if name == "lapse":
                lapse_cap[_span(window, months)] = window.maximum_decrease
        parameters[f"{name}_add"] = addition
        parameters[f"{name}_mult"] = multiplier
    inflation = shocks.get("inflation")
    parameters["inflation_add"] = inflation.additive if inflation is not None else 0.0
    parameters["inflation_mult"] = inflation.multiplicative if inflation is not None else 1.0
    parameters["inflation_months"] = _inflation_months(inflation, months)
    return parameters


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_shock(factors: object, key: str, name: str, months: int) -> Shock:
    if isinstance(factors, list):
        if key not in RATE_SHOCKS or not factors:
            raise ConfigError(f"{name}: {key}: nonempty windows supported for rate shocks only")
        windows = tuple(_parse_shock(f, key, name, months) for f in factors)
        covered: set[int] = set()
        for window in windows:
            if window.start is None or window.end is None or window.windows:
                raise ConfigError(f"{name}: {key}: every window needs Start_Month/End_Month")
            span = set(range(window.start, window.end + 1))
            if covered & span:
                raise ConfigError(f"{name}: {key}: overlapping windows")
            covered.update(span)
        return Shock(0.0, 1.0, windows=windows)
    allowed = {"Additive", "Multiplicative", "Start_Month", "End_Month"}
    if key == "lapse":
        allowed.add("Maximum_Decrease")
    if (
        not isinstance(factors, dict)
        or not factors
        or set(factors) - allowed
        or not {"Additive", "Multiplicative"} & set(factors)
    ):
        raise ConfigError(
            f"{name}: {key}: expected Additive/Multiplicative and optional Start_Month/End_Month"
        )
    start, end = factors.get("Start_Month"), factors.get("End_Month")
    if end == "last":
        end = months - 1
    if (start is None) != (end is None):
        raise ConfigError(f"{name}: {key}: both window months are required")
    if start is not None:
        a, b = (
            finite_number(start, f"{name}: {key}.Start_Month"),
            finite_number(end, f"{name}: {key}.End_Month"),
        )
        if a != int(a) or b != int(b) or not 1 <= a <= b < months:
            raise ConfigError(f"{name}: {key}: invalid projection-month window")
        start, end = int(a), int(b)
    cap = finite_number(factors.get("Maximum_Decrease", 1), f"{name}: {key}.Maximum_Decrease")
    if not 0 <= cap <= 1:
        raise ConfigError(f"{name}: Maximum_Decrease must be in [0, 1]")
    return Shock(
        finite_number(factors.get("Additive", 0), f"{name}: {key}.Additive"),
        finite_number(factors.get("Multiplicative", 1), f"{name}: {key}.Multiplicative"),
        start,
        end,
        cap,
    )


def load_cases(cfg: "RunConfig", root: Path) -> tuple[Case, ...]:
    from avk.runs.overrides import csv_override, parse_overrides

    raw = cfg.cases
    if raw is None:
        if cfg.run_type == "Sensitivities":
            raise ConfigError("Run_Type Sensitivities needs Cases in the run file")
        return ()
    if isinstance(raw, dict):
        if set(raw) != {"CSV"}:
            raise ConfigError("Cases: expected a list or {CSV: path}")
        folder = cfg._path.parent if cfg._path else root
        path = folder / raw["CSV"]
        try:
            fingerprint(path)
            frame = pl.read_csv(path, infer_schema=False)
        except (OSError, pl.exceptions.PolarsError) as exc:
            raise ConfigError(reader_failure("Cases CSV", path, exc)) from exc
        raw = []
        for row in frame.iter_rows(named=True):  # case metadata, never policies
            name = row.get("Name")
            csv_shocks: dict[str, dict[str, object]] = {}
            csv_overrides: dict[str, Any] = {}
            item: dict[str, Any] = {"Name": name, "Shocks": csv_shocks, "Overrides": csv_overrides}
            for column, value in row.items():
                if column == "Name":
                    continue
                parts = column.split(".")
                if csv_override(parts, "" if value is None else value, csv_overrides):
                    continue
                if column != "Mass_Lapse" and (
                    len(parts) != 2
                    or parts[0] not in SHOCK_NAMES
                    or parts[1]
                    not in (
                        "Additive",
                        "Multiplicative",
                        "Start_Month",
                        "End_Month",
                        "Maximum_Decrease",
                    )
                ):
                    raise ConfigError(f"{name}: unknown CSV column {column}")
                if _blank(value):  # an empty cell is not supplied for this case
                    continue
                number = finite_number(value, f"{name}: {column}")
                if column == "Mass_Lapse":
                    item[column] = number
                else:
                    csv_shocks.setdefault(parts[0], {})[parts[1]] = number
            raw.append(item)
    result = []
    seen: set[str] = set()
    for item in raw:
        name = item.get("Name")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]*", name)
            or name.endswith((" ", "."))
        ):
            raise ConfigError(f"Cases: invalid case name {name!r}")
        if name.casefold() in {"base", "cases_impact.csv"} or name.casefold().split(".")[0].rstrip(
            " "
        ) in {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }:
            raise ConfigError(f"Cases: case name {name!r} is reserved")
        for code in cfg.products_to_run:
            if re.fullmatch(
                rf"{re.escape(code)}_Base_(?:aggregate_output|seriatim_output|output)(?:_\d{{8}}_\d{{6}})?\.csv",
                name,
                re.IGNORECASE,
            ):
                raise ConfigError(f"Cases: case name {name!r} is reserved for base output")
        if name.casefold() in seen:
            raise ConfigError("Cases: case names must be unique (ignoring case)")
        seen.add(name.casefold())
        extra = set(item) - {"Name", "Shocks", "Mass_Lapse", "Overrides"}
        if extra:
            raise ConfigError(f"{name}: unknown case fields {sorted(extra)}")
        payload = item.get("Shocks", {} if "Overrides" in item else None)
        if not isinstance(payload, dict):
            raise ConfigError(f"{name}: Shocks must be a mapping")
        shocks = {}
        for key, factors in payload.items():
            if key not in SHOCK_NAMES:
                raise ConfigError(f"{name}: unknown shock {key}")
            if key == "morbidity" and not any(
                code.endswith("_RIDER") for code in cfg.products_to_run
            ):
                raise ConfigError(f"{name}: shock morbidity is not used by this run")
            shocks[key] = _parse_shock(factors, key, name, cfg.projection_term * 12)
        mass = finite_number(item.get("Mass_Lapse", 0), f"{name}: Mass_Lapse")
        if not 0 <= mass <= 1:
            raise ConfigError(f"{name}: Mass_Lapse must be between 0 and 1")
        result.append(Case(name, shocks, mass, parse_overrides(item.get("Overrides", {}), name)))
    return tuple(result)


def _shocked_interest(item: InterestCurveAssumption, shock: Shock) -> InterestCurveAssumption:
    table = item.table
    values = (table.values + shock.additive) * shock.multiplicative
    if not np.isfinite(values).all() or (item.units == "annual_effective" and (values <= -1).any()):
        raise ConfigError(f"{table.name}: shock produces invalid assumption values")
    return item.model_copy(update={"table": replace(table, values=values)})


def case_report(base: "CheckReport", case: Case) -> "CheckReport":
    """The inputs one case projects: the base's, with an interest shock generated into the
    scenarios. Every other shock is a run parameter, validated here before any output."""
    from avk.runs.check import run_factory

    inflation = case.shocks.get("inflation")
    if inflation is not None:
        for context in base.contexts.values():
            if "Inflation" in context.params:
                shifted = (context.params["Inflation"] + inflation.additive) * (
                    inflation.multiplicative
                )
                if not math.isfinite(shifted) or shifted <= -1:
                    raise ConfigError(f"{case.name}: inflation must exceed -1")
    interest = case.shocks.get("interest")
    if interest is None:
        return replace(base, dumps={})
    assert base.scenarios is not None
    if base.scenarios.measure != "deterministic":
        raise ConfigError(
            f"{case.name}: interest shocks require annual curves and the deterministic generator"
        )
    original = base.assumptions.get("interest_rates")
    if not isinstance(original, InterestCurveAssumption):
        raise ConfigError(f"{case.name}: interest shock names no interest_rates curve in this run")
    shocked = _shocked_interest(original, interest)
    curves = {
        name: shocked if name == "interest_rates" else item
        for name, item in base.assumptions.items()
        if isinstance(item, InterestCurveAssumption)
    }
    months = base.config.projection_term * 12
    variables = tuple(
        replace(variable, fiscal_start_month=base.config.fiscal_start_month)
        if variable.fiscal_start_month == "fiscal_start_month"
        else variable
        for variable in run_factory(base.config).assumption_spec().scenario_variables
    )
    scenarios = DeterministicCurveESG(variables).generate(curves, months)
    if interest.start is not None:
        # A window selects the shocked rates in its months only; the curve is not changed.
        mask = np.zeros(months, dtype=bool)
        mask[_span(interest, months)] = True
        scenarios = replace(
            scenarios,
            variables={
                name: np.where(mask, values, base.scenarios.variables[name])
                for name, values in scenarios.variables.items()
            },
        )
        return replace(base, scenarios=scenarios, dumps={})
    return replace(
        base,
        assumptions={**base.assumptions, "interest_rates": shocked},
        tables={**base.tables, "interest_rates": shocked.table},
        scenarios=scenarios,
        dumps={"table__interest_rates": pl.DataFrame(shocked.table.values)},
    )


def impact_rows(
    path: Path, product: str, case: str, baseline: dict[str, float] | None
) -> tuple[list[dict[str, object]], dict[str, float]]:
    generated_file(f"{product}/{case}/aggregate", path)
    frame = pl.read_csv(path, infer_schema_length=None)
    metrics = (
        "cashflows_gross_reserve_pp_reserving",
        "cashflows_net_reserve_pp_reserving",
        "cashflows_be_reserves_BE",
        "MCEV_bel_BE",
        "MCEV_pvfp_BE",
        "MCEV_pv_premium_BE",
        "MCEV_fcc_BE",
        "MCEV_ifrs_bel_BE",
        "cashflows_required_solvency_capital_BE",
    )
    values = frame.row(1, named=True)
    current: dict[str, float] = {}
    row: dict[str, object] = {"Product": product, "Case": case}
    for metric in metrics:
        actual = next(
            (column for column in frame.columns if column.casefold() == metric.casefold()), None
        )
        if actual is None:
            raise ConfigError(f"{product}: impact measure {metric} is absent")
        value = float(values[actual])
        current[metric] = value
        base = baseline[metric] if baseline is not None else value
        row[metric] = value
        row[f"{metric}_change"] = value - base
        row[f"{metric}_change_pct"] = (
            (value - base) / base * 100 if base else (0.0 if value == 0 else None)
        )
    return [row], current
