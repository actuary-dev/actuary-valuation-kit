"""IFRS17 GMM: bounded family projections, independent cases and declared groups."""

import time
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import polars as pl

from avk.model.emit.common import BLOCK
from avk.model.executor import Batch, OutputRequest, Projection, project
from avk.model.kernel import Kernel
from avk.model.measures.ifrs17 import measurement, recognition
from avk.model.measures.ifrs17_rollforward import period_service
from avk.model.measures.stress import (
    Array,
    combine,
    cost_and_pv,
    immediate,
    operational,
    revaluation,
)
from avk.outputs.names import file_name
from avk.outputs.schema import CALENDAR, POLICY, STEP, OutputSchema
from avk.outputs.sinks import CsvSink
from avk.outputs.writers import write_aggregate, write_per_policy_month, write_seriatim
from avk.runs.capital_settings import CapitalSettings, capital_settings, discount_curve
from avk.runs.cases import Case, case_parameters, case_report, load_cases
from avk.runs.check import CheckReport, _check_single, check, run_factory
from avk.runs.compile import product_kernel
from avk.runs.context import RunContext, RunResult
from avk.runs.ifrs17_rollforward_settings import NB_PERIOD, OPENING, PRIOR
from avk.runs.ifrs17_settings import MeasurementSettings, month_date, serial
from avk.runs.overrides import resolve_overrides
from avk.runs.registry import RunType
from avk.runs.stress_capital import _grids, _lower_batch
from avk.runs.stresses import load_stresses
from avk.runs.valuation import _label
from avk.runtime.errors import ConfigError, OutputError

PORTS = {
    "premiums": ("measurement_premiums", None),
    "claims": ("measurement_claims", None),
    "acquisition": ("measurement_acquisition", None),
    "maintenance": ("measurement_maintenance", None),
    "coverage": ("measurement_coverage", None),
    "ri_premiums": ("measurement_ri_premiums", None),
    "ri_recoveries": ("measurement_ri_recoveries", None),
    "claim_expense": ("measurement_claim_expense", None),
    "commissions": ("commissions", "be"),
    "inforce": ("lives_end", "be"),
    "maturities": ("maturities", "be"),
    "sum_assured": ("sum_assured", "be"),
    "reins_sum_assured": ("reins_sum_assured", "be"),
    "onerous_rate": ("fcc_rate", None),
    "ifrs_expense_capital": ("ifrs_expense_capital", None),
}
GROUP_KEYS = ["portfolio", "cohort", "profitability"]


def _rates(
    report: CheckReport, settings: MeasurementSettings, grid: dict[str, Array], lo: int, hi: int
) -> tuple[Array, Array]:
    cohorts = settings.groups["cohort"][lo:hi].to_list()
    locked = settings.locked_rates(
        cohorts, report.config.valuation_date, report.config.projection_term * 12
    )
    current = (
        grid["onerous_rate"]
        if settings.current_curve == "onerous"
        else discount_curve(report, settings.current_curve)
    )
    return current, locked


def _capital_report(
    report: CheckReport,
    root: Path,
    outer_case: Case | None = None,
    scope: tuple[str, ...] | None = None,
) -> CheckReport | None:
    settings = report.measurement
    assert settings is not None
    if settings.ra_method != "cost_of_capital":
        return None
    cfg = report.config.model_copy(
        update={
            "run_type": "StressCapital",
            "ifrs17": None,
            "stress_set": settings.stress_set,
            "cases": None,
            "products_to_run": scope or report.config.products_to_run,
        }
    )
    cfg, stresses = load_stresses(cfg, root)
    cases = load_cases(cfg, root)
    cfg = cfg.model_copy(update={"products_to_run": report.config.products_to_run})
    assert isinstance(cfg.stress_set, dict)
    combined = capital_settings(
        cfg.stress_set, tuple(s.risk for s in stresses), cfg._path.parent if cfg._path else root
    )
    if combined is None:
        raise ConfigError("IFRS17 cost-of-capital RA requires a correlation matrix and Settings")
    if combined.curve != settings.current_curve:
        raise ConfigError("IFRS17 stress Discount_Curve must equal IFRS17.Current_Curve")
    if settings.current_curve == "onerous" and combined.aggregation == "portfolio":
        raise ConfigError("IFRS17 portfolio RA requires one declared shared current curve")
    capital = replace(
        report,
        config=cfg,
        capital_settings=combined,
        stresses=stresses,
        cases=cases,
        case_reports={},
    )
    # All stress projection inputs need the same measurement manifest as the base.
    for case in capital.cases:
        composed = _stress_parameters(
            case_parameters(outer_case, report.config.projection_term * 12),
            case,
            report.config.projection_term * 12,
        )
        child = report
        if case.overrides:
            config, inputs = resolve_overrides(report, case.overrides, root)
            assert report.points is not None
            child = _check_single(config, root=root, inputs=inputs)
            assert child.points is not None
            if not child.points.frame["Policy_Number"].equals(report.points.frame["Policy_Number"]):
                raise ConfigError("IFRS17 risk stress must preserve ordered policy identifiers")
            # Rebuilding changed inputs regenerates scenarios. Apply the outer case's
            # interest shock to those inputs before the additional risk stress.
            if outer_case is not None:
                child = case_report(child, outer_case)
        capital.case_reports[case.name] = case_report(child, case)
        for context in child.contexts.values():
            if "Inflation" in context.params:
                rate = (context.params["Inflation"] + composed["inflation_add"]) * composed[
                    "inflation_mult"
                ]
                if not np.isfinite(rate) or rate <= -1:
                    raise ConfigError("IFRS17 combined inflation must be finite and exceed -1")
    return capital


def _stress_parameters(parameters: dict[str, Any], case: Any, months: int) -> dict[str, Any]:
    """Compose declared case and stress schedules: additions sum, multipliers multiply.

    Both additions apply to the input rate before the product of multipliers. Neutral
    stress schedules therefore preserve every outer-case shock.
    """
    stress = case_parameters(case, months)
    result = dict(parameters)
    for key, value in stress.items():
        if key.endswith("_add"):
            result[key] = parameters[key] + value
        elif key.endswith("_mult"):
            result[key] = parameters[key] * value
        elif key == "lapse_maximum_decrease":
            result[key] = np.minimum(parameters[key], value)
        elif key == "inflation_months":
            inflation = case.shocks.get("inflation")
            if inflation is not None and (inflation.additive != 0 or inflation.multiplicative != 1):
                outer_active = parameters["inflation_add"] != 0 or parameters["inflation_mult"] != 1
                if outer_active and not np.array_equal(
                    np.asarray(parameters[key])[1:], np.asarray(value)[1:]
                ):
                    raise ConfigError("IFRS17 cost RA does not combine differing inflation windows")
                result[key] = value
        elif key == "case_mass_lapse":
            result[key] = 1 - (1 - parameters[key]) * (1 - value)
    if any(not np.isfinite(value).all() for value in result.values()):
        raise ConfigError("IFRS17 combined stress parameters must be finite")
    return result


def _risk_grids(
    report: CheckReport,
    settings: MeasurementSettings,
    capital: CheckReport,
    kernel: Kernel,
    grid: dict[str, Array],
    current_bel: Array,
    names: dict[str, str],
    lo: int,
    hi: int,
    parameters: dict[str, Any],
) -> dict[str, Array]:
    risks: dict[str, Array] = {}
    covered = grid["inforce"] + grid.get("claim_stock", 0.0)
    if report.config.products_to_run[0].endswith("_RIDER"):
        covered = covered + grid["maturities"]
    with np.errstate(divide="ignore", invalid="ignore"):
        pp = current_bel / (grid["inforce"] + grid["maturities"] + grid.get("claim_stock", 0.0))
    for stress, case in zip(capital.stresses, capital.cases, strict=True):
        if stress.method == "mass_lapse":
            assert stress.factor is not None
            values = immediate(grid.get("sv", np.zeros_like(pp)), pp, covered, stress.factor)
        elif stress.method == "catastrophe":
            assert stress.factor is not None
            values = immediate(
                grid["sum_assured"] - grid["reins_sum_assured"], pp, covered, stress.factor
            )
        else:
            child = capital.case_reports[case.name]
            shocked = _grids(
                kernel,
                _lower_batch(
                    child,
                    kernel,
                    _stress_parameters(parameters, case, report.config.projection_term * 12),
                    lo,
                    hi,
                ),
                names,
                batch_size=report.config.batch_size,
            )
            current, locked = _rates(child, settings, shocked, lo, hi)
            value = measurement(shocked, current, locked, 0.0, 0.0)["bel_current"]
            with np.errstate(divide="ignore", invalid="ignore"):
                stressed_pp = value / (
                    shocked["inforce"] + shocked["maturities"] + shocked.get("claim_stock", 0.0)
                )
            values = revaluation(pp, stressed_pp, covered)
        risks[stress.risk] = (
            np.maximum(risks[stress.risk], values) if stress.risk in risks else values
        )
    lapse = [r for r in risks if r.casefold() in ("lapse up", "lapse down", "mass lapse")]
    if lapse:
        risks["lapse"] = np.maximum.reduce([risks[r] for r in lapse])
    return risks


def _project_block(
    report: CheckReport,
    kernel: Kernel,
    names: dict[str, str],
    lo: int,
    hi: int,
    parameters: dict[str, Any],
    schema: OutputSchema | None = None,
) -> tuple[dict[str, Array], Projection]:
    labels = tuple(dict.fromkeys(names.values()))
    grids = {label: np.empty((hi - lo, report.config.projection_term * 12)) for label in labels}

    def receive(batch: Batch) -> None:
        for label in labels:
            grids[label][batch.start : batch.stop] = batch.grids[0, batch.columns.index(label)]

    aggregate = tuple(_label(kernel, c, b) for _, c, b in schema.entries) if schema else ()
    sliced = tuple((_label(kernel, c, b), t) for _, c, b, t in schema.seriatim) if schema else ()
    result = project(
        kernel,
        _lower_batch(report, kernel, parameters, lo, hi),
        OutputRequest(
            aggregate=aggregate, slices=sliced, grids=labels, batch_size=report.config.batch_size
        ),
        on_batch=receive,
    )
    return {key: grids[label] for key, label in names.items()}, result


def _measurement_names(kernel: Kernel) -> dict[str, str]:
    ports = dict(PORTS)
    if ("ifrs_onerous_rate", None) in kernel.layout.keys:
        ports["onerous_rate"] = ("ifrs_onerous_rate", None)
    if ("claim_stock", "be") in kernel.layout.keys:
        ports["claim_stock"] = ("claim_stock", "be")
    if ("sv", "be") in kernel.layout.keys or ("sv", None) in kernel.layout.keys:
        ports["sv"] = ("sv", "be")
    return {name: _label(kernel, column, basis) for name, (column, basis) in ports.items()}


@dataclass(frozen=True)
class _PortfolioRa:
    capital: Array
    undiversified: Array
    current_pv: Array


def _portfolio_ra(
    items: list[tuple[CheckReport, Kernel, dict[str, Any], CheckReport]],
) -> _PortfolioRa:
    """One bounded risk pass over the whole book at one case/date snapshot."""
    combined_settings = items[0][3].capital_settings
    assert combined_settings is not None
    months = items[0][0].config.projection_term * 12
    total_risks = {label: np.zeros(months) for label in combined_settings.labels}
    premiums, bel = np.zeros(months), np.zeros(months)
    shared_curve = None
    for report, kernel, parameters, capital in items:
        settings, points = report.measurement, report.points
        assert settings is not None and points is not None
        names = _measurement_names(kernel)
        for lo in range(0, points.frame.height, BLOCK):
            hi = min(points.frame.height, lo + BLOCK)
            grid, _ = _project_block(report, kernel, names, lo, hi, parameters)
            current, locked = _rates(report, settings, grid, lo, hi)
            common = current[0] if current.ndim == 2 else current
            if (
                current.ndim == 2
                and not np.array_equal(current, np.broadcast_to(common, current.shape))
            ) or (shared_curve is not None and not np.array_equal(common, shared_curve)):
                raise ConfigError("IFRS17 portfolio RA requires one common current curve")
            shared_curve = common
            base = measurement(grid, current, locked, 0.0, settings.ri_ratio)
            risks = _risk_grids(
                report,
                settings,
                capital,
                kernel,
                grid,
                base["bel_current"],
                names,
                lo,
                hi,
                parameters,
            )
            active = settings.groups["recognised"][lo:hi].to_numpy()[:, None]
            premiums = premiums + np.nansum(grid["premiums"] * active, axis=0)
            bel = bel + np.nansum(base["bel_current"] * active, axis=0)
            for label in combined_settings.labels:
                total_risks[label] = total_risks[label] + np.nansum(risks[label] * active, axis=0)
    undiversified = np.stack(list(total_risks.values())).sum(axis=0)
    combined = combine(
        np.stack([total_risks[r] for r in combined_settings.labels], axis=-1),
        combined_settings.correlation,
        combined_settings.floor,
    )["combined"]
    combined = combined + operational(
        premiums, -bel, combined_settings.premium_charge, combined_settings.bel_charge
    )
    assert shared_curve is not None
    value = cost_and_pv(combined, shared_curve, combined_settings.rate, combined_settings.loading)[
        "pv_cost_of_capital"
    ]
    if np.any((undiversified == 0) & (value != 0)):
        raise ConfigError(
            "IFRS17 portfolio RA cannot allocate nonzero RA with zero undiversified capital"
        )
    return _PortfolioRa(combined, undiversified, value)


def _assess(
    report: CheckReport,
    kernel: Kernel,
    parameters: dict[str, Any],
    capital: CheckReport | None,
    *,
    output: Path | None = None,
    diagnostics: Path | None = None,
    portfolio: _PortfolioRa | None = None,
    period_months: int | None = None,
) -> tuple[pl.DataFrame, list[Path]]:
    assert report.measurement is not None and report.points is not None
    settings, cfg, points = report.measurement, report.config, report.points
    count, months = points.frame.height, cfg.projection_term * 12
    names = _measurement_names(kernel)
    risk_names = dict(names)
    combined_settings: CapitalSettings | None = capital.capital_settings if capital else None
    if combined_settings is not None and combined_settings.aggregation == "portfolio":
        assert capital is not None
        if portfolio is None:
            portfolio = _portfolio_ra([(report, kernel, parameters, capital)])
    factory = run_factory(cfg)
    schema = factory.output_schema(cfg.run_type) if output is not None else None
    extra_names: list[str] = []
    if schema:
        for out, column, basis in (*schema.entries, *schema.keys):
            if column not in (POLICY, STEP, CALENDAR):
                names[f"output:{out}"] = _label(kernel, column, basis)
    policies: list[pl.DataFrame] = []
    files: list[Path] = []
    aggregate: dict[str, Array] = {}
    ordinary_slices: dict[str, list[Array]] = {}
    sink = CsvSink(output) if output is not None else None
    with ExitStack() as stack:
        stream = None
        diagnostic_stream = None
        if sink and cfg.output_seriatim_cf_flag:
            name = file_name(factory.code, "Base", "output")
            stream = stack.enter_context(sink.open_stream(name))
            files.append(sink.path(name))
        if diagnostics is not None:
            diagnostics.mkdir(parents=True, exist_ok=True)
            diagnostic_stream = stack.enter_context(CsvSink(diagnostics).open_stream("ifrs17"))
        for lo in range(0, count, BLOCK):
            hi = min(lo + BLOCK, count)
            grid, projected = _project_block(report, kernel, names, lo, hi, parameters, schema)
            current, locked = _rates(report, settings, grid, lo, hi)
            measured = measurement(grid, current, locked, settings.ra_ratio, settings.ri_ratio)
            risks = {}
            if combined_settings is not None:
                assert capital is not None
                risks = _risk_grids(
                    report,
                    settings,
                    capital,
                    kernel,
                    grid,
                    measured["bel_current"],
                    risk_names,
                    lo,
                    hi,
                    parameters,
                )
                risk_stack = np.stack([risks[r] for r in combined_settings.labels], axis=-1)
                measured["undiversified_capital"] = np.nansum(risk_stack, axis=-1)
                if combined_settings.aggregation == "policy":
                    total = combine(
                        risk_stack, combined_settings.correlation, combined_settings.floor
                    )["combined"]
                    total = total + operational(
                        grid["premiums"],
                        -measured["bel_current"],
                        combined_settings.premium_charge,
                        combined_settings.bel_charge,
                    )
                    for basis, rates in (("current", current), ("locked", locked)):
                        measured[f"ra_{basis}"] = cost_and_pv(
                            total, rates, combined_settings.rate, combined_settings.loading
                        )["pv_cost_of_capital"]
                else:
                    assert portfolio is not None
                    weights = np.divide(
                        measured["undiversified_capital"],
                        portfolio.undiversified,
                        out=np.zeros_like(measured["undiversified_capital"]),
                        where=portfolio.undiversified > 0,
                    )
                    weights = weights * settings.groups["recognised"][lo:hi].to_numpy()[:, None]
                    measured["ra_current"] = weights * portfolio.current_pv
                    locked_total = cost_and_pv(
                        np.broadcast_to(portfolio.capital, locked.shape),
                        locked,
                        combined_settings.rate,
                        combined_settings.loading,
                    )["pv_cost_of_capital"]
                    measured["ra_locked"] = weights * locked_total
            # Policy diagnostics retain every month; policy output retains the feed's time-0 slice.
            ids = points.frame["Policy_Number"][lo:hi].cast(pl.String)
            policy = {name: value[:, 0] for name, value in measured.items()}
            policy["coverage_units_total"] = np.nansum(measured["coverage_units"], axis=1)
            if period_months is not None:
                for name in ("bel_locked", "ra_locked", "ri_bel_locked", "ri_ra_locked"):
                    policy[f"expected_{name}"] = measured[name][:, period_months]
                policy.update(
                    period_service(
                        measured["coverage_units"],
                        grid["inforce"],
                        measured["claims"] + measured["claim_expense"],
                        measured["maintenance"],
                        measured["ra_locked"],
                        locked,
                        period_months,
                    )
                )
            policies.append(pl.DataFrame({"Policy_Number": ids, **policy}))
            if schema:
                for i, (out, _, _) in enumerate(schema.entries):
                    aggregate[out] = (
                        aggregate.get(out, np.zeros(months)) + projected.aggregate[0, i]
                    )
                for i, (out, _, _, _) in enumerate(schema.seriatim):
                    ordinary_slices.setdefault(out, []).append(projected.slices[0, i])
                extra_names = [f"IFRS17_{name}" for name in measured]
                extended = replace(
                    schema, entries=(*schema.entries, *((name, name, None) for name in extra_names))
                )
                columns = {
                    out: grid[f"output:{out}"]
                    for out, c, _ in (*schema.keys, *schema.entries)
                    if c not in (POLICY, STEP, CALENDAR)
                }
                columns.update({f"IFRS17_{name}": value for name, value in measured.items()})
                for name, value in measured.items():
                    key = f"IFRS17_{name}"
                    aggregate[key] = aggregate.get(key, np.zeros(months)) + np.nansum(value, axis=0)
                if stream is not None:
                    write_per_policy_month(
                        stream,
                        extended,
                        ids,
                        columns,
                        calendar=(cfg.valuation_date.month - 1 + np.arange(months)) % 12 + 1,
                    )
            if diagnostic_stream is not None:
                diagnostic_stream.append(
                    pl.DataFrame(
                        {
                            "Policy_Number": np.repeat(ids.to_numpy(), months),
                            "Projection_Step": np.tile(np.arange(months), hi - lo),
                            **{n: v.reshape(-1) for n, v in measured.items()},
                            **{f"capital_{n}": v.reshape(-1) for n, v in risks.items()},
                            "current_rate": np.broadcast_to(current, (hi - lo, months)).reshape(-1),
                            "locked_rate": locked.reshape(-1),
                            "commissions": grid["commissions"].reshape(-1),
                            "inforce": grid["inforce"].reshape(-1),
                        }
                    )
                )
    if sink and schema:
        extended = replace(schema, entries=(*schema.entries, *((n, n, None) for n in extra_names)))
        files.append(
            write_aggregate(
                sink,
                file_name(factory.code, "Base", "aggregate_output"),
                extended,
                aggregate,
            )
        )
        files.append(
            write_seriatim(
                sink,
                file_name(factory.code, "Base", "seriatim_output"),
                schema,
                points.frame["Policy_Number"].cast(pl.String),
                {name: np.concatenate(values) for name, values in ordinary_slices.items()},
            )
        )
    return pl.concat(policies), files


def _prepare(
    report: CheckReport,
    root: Path,
    scope: tuple[str, ...] | None = None,
    issues: dict[str, list[Any]] | None = None,
) -> list[Any]:
    """Prove every case and issue-date input before any product writes output."""
    prepared = []
    for case in (None, *report.cases):
        child = report if case is None else report.case_reports[case.name]
        assert child.measurement is not None and child.points is not None
        settings = child.measurement
        capital = _capital_report(child, root, case, scope)
        dates = (
            settings.groups.filter(pl.col("recognised_new_business"))["start"]
            .dt.truncate("1mo")
            .unique()
            .sort()
            .to_list()
        )
        if issues is not None:
            dates = issues[case.name if case else "Base"]
        recognitions = []
        for issue in dates:
            when = month_date(serial(issue) - 1, end=True)
            cfg = child.config.model_copy(update={"valuation_date": when, "cases": None})
            earlier = _check_single(cfg, root=root, inputs=child.inputs, raw=child.points.frame)
            earlier.measurement = replace(
                settings,
                groups=settings.groups.with_columns(
                    (pl.col("start") <= month_date(serial(issue), end=True)).alias("recognised")
                ),
            )
            if case is not None:
                earlier = case_report(earlier, case)
            recognitions.append((issue, earlier, _capital_report(earlier, root, case, scope)))
        prepared.append((case, child, capital, recognitions))
    return prepared


class IFRS17(RunType):
    name = "IFRS17"
    parameters = MappingProxyType({"mask_step0_reserve": 1.0})

    def execute(self, ctx: RunContext) -> RunResult:
        try:
            return self._execute(ctx)
        except OSError as exc:
            raise OutputError(f"Cannot write IFRS17 output: {exc}") from exc

    def _execute(self, ctx: RunContext) -> RunResult:
        begun = time.perf_counter()
        report = check(ctx.config, root=ctx.root, dump_inputs=ctx.diagnostics)
        products = report.products or {ctx.config.products_to_run[0]: report}
        if report.products:
            products = {
                code: replace(
                    child,
                    cases=report.cases,
                    case_reports={
                        case.name: report.case_reports[case.name].products[code]
                        for case in report.cases
                    },
                )
                for code, child in products.items()
            }
        issues = {}
        for case in (None, *report.cases):
            name = case.name if case else "Base"
            dates = set()
            for child in products.values():
                selected = child if case is None else child.case_reports[name]
                assert selected.measurement is not None
                dates.update(
                    selected.measurement.groups.filter(pl.col("recognised_new_business"))["start"]
                    .dt.truncate("1mo")
                    .unique()
                    .to_list()
                )
            issues[name] = sorted(dates)
        prepared = {
            code: _prepare(child, ctx.root, ctx.config.products_to_run, issues)
            for code, child in products.items()
        }
        kernels = {
            code: product_kernel(run_factory(child.config).definition(), device=child.config.device)
            for code, child in products.items()
        }
        portfolios: dict[tuple[str, date | None], _PortfolioRa] = {}
        for index, case in enumerate((None, *report.cases)):
            name = case.name if case else "Base"
            for snapshot_index, issue in enumerate((None, *issues[name])):
                items = []
                for code, entries in prepared.items():
                    _, child, capital, recognitions = entries[index]
                    if capital is None or capital.capital_settings.aggregation != "portfolio":
                        continue
                    if issue is not None:
                        _, child, capital = recognitions[snapshot_index - 1]
                    params = {
                        **self.parameters,
                        **case_parameters(case, child.config.projection_term * 12),
                    }
                    items.append((child, kernels[code], params, capital))
                if items:
                    portfolios[(name, issue)] = _portfolio_ra(items)
        results = []
        impacts = []
        captured: dict[tuple[str, str], pl.DataFrame] = {}
        period = None
        if report.rollforward_balances is not None:
            first_settings = next(iter(products.values())).measurement
            assert first_settings is not None
            period = first_settings.reporting_months
        for code, child in products.items():
            kernel = kernels[code]
            child_ctx = replace(
                ctx,
                config=child.config,
                diagnostics=(
                    ctx.diagnostics / code
                    if ctx.diagnostics is not None and report.products
                    else ctx.diagnostics
                ),
            )
            result, rows = self._execute_product(
                child_ctx,
                child,
                kernel,
                prepared[code],
                portfolios,
                captured=captured if period is not None else None,
                period_months=period,
            )
            results.append(result)
            impacts.extend(rows)
        impact_file = CsvSink(ctx.output).write_table("cases_impact", pl.DataFrame(impacts))
        rollforward_files: tuple[Path, ...] = ()
        if report.rollforward_balances is not None:
            from avk.runs.ifrs17_rollforward import build_rollforward

            rollforward_files = (
                CsvSink(ctx.output).write_table(
                    "IFRS17_rollforward", build_rollforward(report, captured)
                ),
            )
        return RunResult(
            self.name,
            (
                *tuple(path for result in results for path in result.files),
                impact_file,
                *rollforward_files,
            ),
            {code: value for result in results for code, value in result.kernels.items()},
            {"total": time.perf_counter() - begun},
            tuple(report.notes),
            ctx.diagnostics,
            cache_hits={
                code: value for result in results for code, value in result.cache_hits.items()
            },
        )

    @staticmethod
    def _recognise(
        kernel: Kernel,
        child: CheckReport,
        recognitions: list[Any],
        params: dict[str, Any],
        portfolios: dict[tuple[str, date | None], _PortfolioRa],
        name: str,
        *,
        period: bool,
    ) -> pl.DataFrame | None:
        """Per-policy new-business balances at each issue month's recognition snapshot."""
        assert child.measurement is not None
        keys = child.measurement.groups
        frames = []
        for issue, earlier, earlier_capital in recognitions:
            mask = keys["start"].dt.truncate("1mo") == issue
            if not mask.any():
                continue
            duration = serial(child.config.valuation_date) - serial(issue) + 1
            old, _ = _assess(
                earlier,
                kernel,
                params,
                earlier_capital,
                portfolio=portfolios.get((name, issue)),
                period_months=duration if period else None,
            )
            old = old.filter(mask)
            selected_keys = keys.filter(mask)
            locked = child.measurement.locked_rates(
                selected_keys["cohort"].to_list(), issue, duration
            )
            balances = recognition(
                old["bel_locked"].to_numpy(),
                old["ra_locked"].to_numpy(),
                old["ri_bel_locked"].to_numpy(),
                old["ri_ra_locked"].to_numpy(),
                old["pv_claims"].to_numpy(),
                old["pv_recoveries"].to_numpy(),
                np.prod(1 + locked, axis=1),
            )
            if period:
                # New business is in force at closing: its service is the cover actually
                # provided from recognition to closing.
                growth = np.prod(1 + locked, axis=1) - 1.0
                balances["nb_coverage_units"] = old["survivor_coverage_units"].to_numpy()
                balances["nb_released_outflows"] = old["released_outflows"].to_numpy()
                balances["nb_loss_interest"] = balances["loss_component"] * growth
                balances["nb_recovery_interest"] = balances["loss_recovery_component"] * growth
            frames.append(pl.DataFrame({"Policy_Number": old["Policy_Number"], **balances}))
        return pl.concat(frames) if frames else None

    def _execute_product(
        self,
        ctx: RunContext,
        report: CheckReport,
        kernel: Kernel,
        prepared: list[Any],
        portfolios: dict[tuple[str, date | None], _PortfolioRa],
        *,
        captured: dict[tuple[str, str], pl.DataFrame] | None = None,
        period_months: int | None = None,
    ) -> tuple[RunResult, list[Any]]:
        code = report.config.products_to_run[0]
        files: list[Path] = []
        impacts = []
        baseline: dict[str, float] = {}
        rolling = period_months is not None
        entries = {(entry[0].name if entry[0] else "Base"): entry for entry in prepared}
        recognised_frames: dict[str, pl.DataFrame | None] = {}

        def recognise(name: str) -> pl.DataFrame | None:
            # Roll-forward new business is recognised once, under opening assumptions; the
            # closing case reuses those balances so every saved report shares one group.
            source = PRIOR if rolling and name == "Base" else name
            if source not in recognised_frames:
                case, child, _, recognitions = entries[source]
                recognised_frames[source] = self._recognise(
                    kernel,
                    child,
                    recognitions,
                    {**self.parameters, **case_parameters(case, child.config.projection_term * 12)},
                    portfolios,
                    source,
                    period=rolling and source == PRIOR,
                )
            return recognised_frames[source]

        for case, child, capital, _ in prepared:
            name = case.name if case else "Base"
            folder = ctx.output / name if case else ctx.output
            diagnostic = ctx.diagnostics / name if ctx.diagnostics is not None else None
            params = {**self.parameters, **case_parameters(case, child.config.projection_term * 12)}
            values, output = _assess(
                child,
                kernel,
                params,
                capital,
                output=folder,
                diagnostics=diagnostic,
                portfolio=portfolios.get((name, None)),
                period_months=period_months if rolling and name == OPENING else None,
            )
            files.extend(output)
            assert child.measurement is not None
            keys = child.measurement.groups
            frame = recognise(name)
            if frame is not None:
                values = values.join(frame, on="Policy_Number", how="left")
            else:
                zero = np.zeros(1)
                for n in recognition(zero, zero, zero, zero, zero, zero, np.ones(1)):
                    values = values.with_columns(pl.lit(0.0).alias(n))
            if rolling and name != OPENING:
                for n in NB_PERIOD:
                    if n not in values.columns:
                        values = values.with_columns(pl.lit(0.0).alias(n))
            numeric = [n for n in values.columns if n != "Policy_Number"]
            values = keys.join(values, on="Policy_Number", how="left").with_columns(
                pl.col(numeric).fill_null(0.0),
                pl.when(
                    pl.col("recognised_new_business") & pl.lit(not (rolling and name == OPENING))
                )
                .then(
                    pl.when(pl.col("recognition_fcf").fill_null(0) > 0)
                    .then(pl.lit("onerous"))
                    .otherwise(pl.lit("other"))
                )
                .otherwise(pl.col("profitability"))
                .alias("profitability"),
            )
            # Logical grouping across the whole policy result (one row/policy), independent
            # of physical batches. Month grids remain bounded within _assess.
            recognised = values.filter(pl.col("recognised"))
            if captured is not None:
                captured[(code, name)] = values
            group = recognised.group_by(GROUP_KEYS, maintain_order=True).agg(
                pl.col(numeric).sum(), pl.len().alias("policies")
            )
            sink = CsvSink(folder)
            files.append(sink.write_table(file_name(code, self.name, "policy_output"), values))
            files.append(sink.write_table(file_name(code, self.name, "group_output"), group))
            metrics = {
                n: float(group[n].sum())
                for n in (
                    "bel_current",
                    "ra_current",
                    "csm_at_recognition",
                    "loss_component",
                    "ri_bel_current",
                    "ri_ra_current",
                    "ri_csm_at_recognition",
                    "loss_recovery_component",
                )
            }
            if case is None:
                baseline = metrics
            impacts.append(
                {
                    "Product": code,
                    "Case": name,
                    **metrics,
                    **{f"{n}_change": v - baseline[n] for n, v in metrics.items()},
                    **{
                        f"{n}_change_pct": (v - baseline[n]) / baseline[n] * 100
                        if baseline[n]
                        else (0.0 if v == 0 else None)
                        for n, v in metrics.items()
                    },
                }
            )
        return RunResult(
            self.name,
            tuple(files),
            {code: kernel.identity},
            {},
            tuple(report.notes),
            ctx.diagnostics,
            cache_hits={code: kernel.cache_hit},
        ), impacts
