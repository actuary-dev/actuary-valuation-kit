"""Stress capital I: one compiled product, checked cases, bounded batch measures."""

import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

import numpy as np
import polars as pl

from avk.assumptions.lowering import lower
from avk.model.data import ModelPoints
from avk.model.emit.common import BLOCK
from avk.model.executor import Batch, KernelInputs, OutputRequest, project
from avk.model.kernel import Kernel
from avk.model.measures.stress import (
    Array,
    combine,
    cost_and_pv,
    immediate,
    operational,
    revaluation,
)
from avk.outputs.names import file_name
from avk.outputs.sinks import CsvSink
from avk.products.diagnostics import ProjectionRecorder
from avk.runs.capital_settings import discount_curve
from avk.runs.cases import case_parameters
from avk.runs.check import CheckReport, check, run_factory
from avk.runs.compile import product_kernel
from avk.runs.context import RunContext, RunResult
from avk.runs.registry import RunType
from avk.runs.valuation import _label, _write_dumps
from avk.runtime.errors import OutputError

METRICS = {
    "diversified": "diversified_capital",
    "combined": "combined_capital",
    "operational": "operational_risk",
    "total": "total_capital",
    "cost_of_capital": "cost_of_capital",
    "pv_cost_of_capital": "pv_cost_of_capital",
}


@dataclass
class _CapitalTotals:
    risks: dict[str, Array]
    measures: dict[str, Array]
    premiums: Array
    bel: Array
    rates: Array | None = None  # the validated monthly discount curve, resolved once per product


def _capital_frame(totals: dict[str, Array], measures: dict[str, Array]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Projection_Step": np.arange(len(next(iter(totals.values())))),
            **{f"capital_{r}": v for r, v in totals.items()},
            **{METRICS[m]: v for m, v in measures.items()},
        }
    )


def _diagnostic(
    path: Path, columns: dict[str, Array], ids: Array, months: int, append: bool
) -> None:
    """One wide row per policy-month, one column per grid, appended block by block."""
    if not columns:
        return
    frame = pl.DataFrame(
        {
            "Policy_Number": np.repeat(ids, months),
            "Projection_Step": np.tile(np.arange(months), len(ids)),
            **{name: grid.reshape(-1) for name, grid in columns.items()},
        }
    )
    with path.open("a" if append else "w") as stream:
        frame.write_csv(stream, include_header=not append)


def _lower_batch(
    report: CheckReport, kernel: Kernel, parameters: Mapping[str, float | Array], lo: int, hi: int
) -> KernelInputs:
    assert report.points is not None and report.scenarios is not None
    points = ModelPoints(report.points.frame.slice(lo, hi - lo), report.points.fields)
    return lower(report.contexts, points, report.scenarios, kernel, parameters)


def _columns(kernel: Kernel) -> dict[str, str]:
    names = {
        name: _label(kernel, name, "be")
        for name in (
            "bel_pp",
            "lives_end",
            "lives_begin",
            "maturities",
            "sum_assured",
            "reins_sum_assured",
        )
    }
    for name in ("claim_stock", "sv"):
        if (name, "be") in kernel.layout.keys or (name, None) in kernel.layout.keys:
            names[name] = _label(kernel, name, "be")
    return names


def _grids(
    kernel: Kernel,
    inputs: KernelInputs,
    names: dict[str, str],
    *,
    batch_size: int,
    recorder: ProjectionRecorder | None = None,
    offset: int = 0,
) -> dict[str, Array]:
    grids = {name: np.empty((inputs.policies, inputs.months)) for name in names}

    def receive(batch: Batch) -> None:
        for name, label in names.items():
            grids[name][batch.start : batch.stop] = batch.grids[0, batch.columns.index(label)]
        if recorder is not None:
            recorder.add(replace(batch, start=batch.start + offset, stop=batch.stop + offset))

    project(
        kernel,
        inputs,
        OutputRequest(
            grids=tuple(names.values()), batch_size=batch_size, diagnostics=recorder is not None
        ),
        on_batch=receive,
    )
    return grids


class StressCapital(RunType):
    name = "StressCapital"
    parameters = MappingProxyType({"mask_step0_reserve": 0.0})

    def execute(self, ctx: RunContext) -> RunResult:
        begun = time.perf_counter()
        report = check(ctx.config, root=ctx.root, dump_inputs=ctx.diagnostics)
        products = report.products or {ctx.config.products_to_run[0]: report}
        kernels = {
            code: product_kernel(run_factory(child.config).definition(), device=child.config.device)
            for code, child in products.items()
        }
        files: list[Path] = []
        months = ctx.config.projection_term * 12
        portfolio = _CapitalTotals({}, {}, np.zeros(months), np.zeros(months))
        rows = []
        try:
            for code, child in products.items():
                output, totals = self._product(ctx, report, child, code, kernels[code])
                files.extend(output)
                if report.capital_settings is not None:
                    for target, source in (
                        (portfolio.risks, totals.risks),
                        (portfolio.measures, totals.measures),
                    ):
                        for key, value in source.items():
                            target[key] = target.get(key, np.zeros_like(value)) + value
                    portfolio.premiums = portfolio.premiums + totals.premiums
                    portfolio.bel = portfolio.bel + totals.bel
                    portfolio.rates = totals.rates
                    rows.append(self._impact(code, totals.measures))
            settings = report.capital_settings
            if settings is not None:
                if len(products) > 1:
                    if settings.aggregation == "portfolio":
                        portfolio.measures.update(
                            combine(
                                np.stack([portfolio.risks[r] for r in settings.labels], axis=-1),
                                settings.correlation,
                                settings.floor,
                            )
                        )
                        portfolio.measures["operational"] = operational(
                            portfolio.premiums,
                            portfolio.bel,
                            settings.premium_charge,
                            settings.bel_charge,
                        )
                        portfolio.measures["total"] = (
                            portfolio.measures["combined"] + portfolio.measures["operational"]
                        )
                        assert portfolio.rates is not None  # check proved the curves identical
                        portfolio.measures.update(
                            cost_and_pv(
                                portfolio.measures["total"],
                                portfolio.rates,
                                settings.rate,
                                settings.loading,
                            )
                        )
                    files.append(
                        CsvSink(ctx.output).write_table(
                            file_name("Portfolio", self.name, "aggregate_output"),
                            _capital_frame(portfolio.risks, portfolio.measures),
                        )
                    )
                    rows.append(self._impact("Portfolio", portfolio.measures))
                base_rows = [
                    {
                        "Product": row["Product"],
                        "Case": "Base",
                        **{k: 0.0 for k in row if k not in ("Product", "Case")},
                    }
                    for row in rows
                ]
                impact = []
                for row in base_rows + rows:
                    changes = {
                        f"{k}_change": v for k, v in row.items() if k not in ("Product", "Case")
                    }
                    percentages = {
                        f"{k}_change_pct": 0.0 if v == 0 else None
                        for k, v in row.items()
                        if k not in ("Product", "Case")
                    }
                    impact.append({**row, **changes, **percentages})
                files.append(CsvSink(ctx.output).write_table("cases_impact", pl.DataFrame(impact)))
        except OSError as exc:
            raise OutputError(f"Cannot write stress-capital outputs: {exc}") from exc
        return RunResult(
            self.name,
            tuple(files),
            {c: k.identity for c, k in kernels.items()},
            {"total": time.perf_counter() - begun},
            tuple(report.notes),
            ctx.diagnostics,
            cache_hits={c: k.cache_hit for c, k in kernels.items()},
        )

    @staticmethod
    def _impact(code: str, totals: dict[str, Array]) -> dict[str, str | float]:
        metrics = {
            METRICS[r]: float(totals[r][1])
            for r in ("combined", "operational", "total", "cost_of_capital", "pv_cost_of_capital")
        }
        return {"Product": code, "Case": "StressCapital", **metrics}

    def _product(
        self,
        ctx: RunContext,
        report: CheckReport,
        base: CheckReport,
        code: str,
        kernel: Kernel,
    ) -> tuple[list[Path], _CapitalTotals]:
        assert base.points is not None and base.scenarios is not None
        months, policies = base.config.projection_term * 12, base.points.frame.height
        names = _columns(kernel)
        settings = report.capital_settings
        rates = None
        if settings is not None:
            names.update({n: _label(kernel, n, "be") for n in ("bel", "premium_income")})
            rates = discount_curve(base, settings.curve)  # one curve for every block
        prepared = {"Base": base}
        run_parameters = {"Base": {**self.parameters, **case_parameters(None, months)}}
        recorders = {}
        if ctx.diagnostics is not None:
            factory = run_factory(base.config)
            for name in ("Base", *(s.name for s in report.stresses if s.method == "revaluation")):
                recorders[name] = factory.diagnostics().projection_recorder(
                    base.points.frame["Policy_Number"].cast(pl.String), base.config.batch_size
                )
        for stress, case in zip(report.stresses, report.cases, strict=True):
            child = report.case_reports[case.name]
            child = child.products[code] if child.products else child
            assert child.points is not None and child.scenarios is not None
            if stress.method == "revaluation":
                parameters = {**self.parameters, **case_parameters(case, months)}
                prepared[case.name] = child
                run_parameters[case.name] = parameters
                if ctx.diagnostics is not None:
                    _write_dumps(
                        ctx.diagnostics / case.name / code,
                        {
                            **child.dumps,
                            "case_parameters": pl.DataFrame(
                                {
                                    "Projection_Step": np.arange(months),
                                    **{
                                        k: np.broadcast_to(np.asarray(v, np.float64), (months,))
                                        for k, v in parameters.items()
                                    },
                                }
                            ),
                            "scenarios": pl.DataFrame(
                                {k: v[0] for k, v in child.scenarios.variables.items()}
                            ),
                        },
                    )
        risks = list(dict.fromkeys(stress.risk for stress in report.stresses))
        lapse_risks = [r for r in risks if r.casefold() in ("lapse up", "lapse down", "mass lapse")]
        if lapse_risks:
            risks.append("lapse")
        totals = {risk: np.zeros(months) for risk in risks}
        slices: dict[str, list[Array]] = {risk: [] for risk in risks}
        measures: dict[str, Array] = {}
        measure_slices: dict[str, list[Array]] = {}
        if settings is not None:
            for metric in (
                "diversified",
                "combined",
                "operational",
                "total",
                "cost_of_capital",
                "pv_cost_of_capital",
            ):
                measures[metric] = np.zeros(months)
                if settings.aggregation == "policy":
                    measure_slices[metric] = []
        portfolio_premiums, portfolio_bel = np.zeros(months), np.zeros(months)
        ctx.output.mkdir(parents=True, exist_ok=True)
        diagnostic = None
        if ctx.diagnostics is not None:
            folder = ctx.diagnostics / code
            folder.mkdir(parents=True, exist_ok=True)
            diagnostic = folder / "stress_capital.csv"
        # A logical block is invariant to physical Batch_Size. Never keep whole-book grids.
        for lo in range(0, policies, BLOCK):
            hi = min(lo + BLOCK, policies)
            grid = _grids(
                kernel,
                _lower_batch(base, kernel, run_parameters["Base"], lo, hi),
                names,
                batch_size=base.config.batch_size,
                recorder=recorders.get("Base"),
                offset=lo,
            )
            inforce = grid["lives_end"]
            if code.endswith("_RIDER"):
                inforce = inforce + grid["maturities"] + grid.get("claim_stock", 0.0)
            capital: dict[str, Array] = {}
            for stress, case in zip(report.stresses, report.cases, strict=True):
                if stress.method == "mass_lapse":
                    assert stress.factor is not None
                    values = immediate(
                        grid.get("sv", np.zeros_like(inforce)),
                        grid["bel_pp"],
                        inforce,
                        stress.factor,
                    )
                elif stress.method == "catastrophe":
                    assert stress.factor is not None
                    values = immediate(
                        grid["sum_assured"] - grid["reins_sum_assured"],
                        grid["bel_pp"],
                        inforce,
                        stress.factor,
                    )
                else:
                    shocked = _grids(
                        kernel,
                        _lower_batch(
                            prepared[case.name], kernel, run_parameters[case.name], lo, hi
                        ),
                        {"bel_pp": names["bel_pp"]},
                        batch_size=base.config.batch_size,
                        recorder=recorders.get(case.name),
                        offset=lo,
                    )
                    values = revaluation(grid["bel_pp"], shocked["bel_pp"], inforce)
                capital[stress.risk] = (
                    np.maximum(capital[stress.risk], values) if stress.risk in capital else values
                )
            if lapse_risks:
                capital["lapse"] = np.maximum.reduce([capital[r] for r in lapse_risks])
            measured: dict[str, Array] = {}
            if settings is not None:
                if settings.aggregation == "policy":
                    measured.update(
                        combine(
                            np.stack([capital[r] for r in settings.labels], axis=-1),
                            settings.correlation,
                            settings.floor,
                        )
                    )
                    measured["operational"] = operational(
                        grid["premium_income"],
                        grid["bel"],
                        settings.premium_charge,
                        settings.bel_charge,
                    )
                    measured["total"] = measured["combined"] + measured["operational"]
                    assert rates is not None
                    measured.update(
                        cost_and_pv(measured["total"], rates, settings.rate, settings.loading)
                    )
                else:
                    portfolio_premiums = portfolio_premiums + np.nansum(
                        grid["premium_income"], axis=0
                    )
                    portfolio_bel = portfolio_bel + np.nansum(grid["bel"], axis=0)
            ids = base.points.frame["Policy_Number"][lo:hi].cast(pl.String).to_numpy()
            # Undefined (0/0) expired-policy tails stay NaN in the policy grids, as in the old
            # model, and every reduction skips them. Those months carry no in-force, so the
            # skipped cells hold no capital under either aggregation method.
            for risk, values in capital.items():
                totals[risk] = totals[risk] + np.nansum(values, axis=0)
                slices[risk].append(values[:, 1].copy())
            for metric, values in measured.items():
                measures[metric] = measures[metric] + np.nansum(values, axis=0)
                measure_slices[metric].append(values[:, 1].copy())
            if diagnostic is not None:
                _diagnostic(
                    diagnostic, {f"capital_{r}": v for r, v in capital.items()}, ids, months, lo > 0
                )
                _diagnostic(
                    diagnostic.with_name("stress_measures.csv"),
                    {METRICS[m]: v for m, v in measured.items()},
                    ids,
                    months,
                    lo > 0,
                )
        if settings is not None and settings.aggregation == "portfolio":
            measures.update(
                combine(
                    np.stack([totals[r] for r in settings.labels], axis=-1),
                    settings.correlation,
                    settings.floor,
                )
            )
            measures["operational"] = operational(
                portfolio_premiums, portfolio_bel, settings.premium_charge, settings.bel_charge
            )
            measures["total"] = measures["combined"] + measures["operational"]
            assert rates is not None
            measures.update(cost_and_pv(measures["total"], rates, settings.rate, settings.loading))
        sink = CsvSink(ctx.output)
        aggregate = sink.write_table(
            file_name(code, "StressCapital", "aggregate_output"),
            _capital_frame(totals, measures),
        )
        seriatim = sink.write_table(
            file_name(code, "StressCapital", "seriatim_output"),
            pl.DataFrame(
                {
                    "Policy_Number": base.points.frame["Policy_Number"],
                    **{f"capital_{r}": np.concatenate(v) for r, v in slices.items()},
                    **{METRICS[m]: np.concatenate(v) for m, v in measure_slices.items()},
                }
            ),
        )
        if ctx.diagnostics is not None:
            for name, recorder in recorders.items():
                _write_dumps(ctx.diagnostics / name / code, recorder.dumps())
        return [aggregate, seriatim], _CapitalTotals(
            totals, measures, portfolio_premiums, portfolio_bel, rates
        )
