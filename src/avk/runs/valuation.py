"""Project the book and write valuation outputs.

The input gate is `check`'s, so `check` and `run` validate the same declared inputs. The
aggregate is summed in the kernel; the seriatim file (one row per policy) is sliced in the
kernel at the steps the schema names; the per-policy-month file (`Output_seriatim_cf_flag` 1)
is streamed batch by batch; `--diagnostics` writes every column of every policy-month (of the
first scenario), plus the input dumps `check --dump-inputs` writes. A deterministic run
projects a single path; a supplied scenario set projects every path in the
same kernel call and leads each file with a `Scenario` column. Product-generic: names come
from the factory. A Valuation keeps the net reserve at the valuation instant
(`mask_step0_reserve` is 0).
"""

import mmap
import tempfile
import time
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import numpy as np
import numpy.typing as npt
import polars as pl

from avk.assumptions.lowering import lower
from avk.model.data import ModelPoints
from avk.model.emit.common import BLOCK
from avk.model.executor import Batch, OutputRequest, Projection, project
from avk.model.kernel import Kernel
from avk.outputs.names import file_name
from avk.outputs.schema import CALENDAR, POLICY, STEP, OutputSchema
from avk.outputs.sinks import CsvSink, CsvStream
from avk.outputs.writers import (
    write_aggregate,
    write_per_policy_month,
    write_scenario_summary,
    write_seriatim,
)
from avk.runs.batching import batch_size
from avk.runs.cases import case_parameters, impact_rows
from avk.runs.check import CheckReport, check, run_factory
from avk.runs.compile import product_kernel
from avk.runs.context import RunContext, RunResult
from avk.runs.registry import RunType
from avk.runs.scenario_statistics import summarize
from avk.runtime.errors import ConfigError, OutputError

BASE = "Base"


def _label(kernel: Kernel, column: str, basis: str | None) -> str:
    """The kernel column an output entry reads: its basis's own, else the shared one."""
    for key in ((column, basis), (column, None)):
        if key in kernel.layout.keys:
            return kernel.columns[kernel.layout.keys.index(key)]
    raise ConfigError(f"Output column {column} on basis {basis} is not computed by the kernel")


def _write_dumps(folder: Path, dumps: Mapping[str, pl.DataFrame]) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for stem, frame in dumps.items():
            frame.write_parquet(folder / f"{stem}.parquet")
    except OSError as exc:
        raise OutputError(f"Cannot write diagnostics to {folder}: {exc}") from exc


class Valuation(RunType):
    name = "Valuation"
    parameters = MappingProxyType({"mask_step0_reserve": 0.0})

    def execute(self, ctx: RunContext) -> RunResult:
        begun = time.perf_counter()
        report = check(ctx.config, root=ctx.root, dump_inputs=ctx.diagnostics)
        if ctx.config.cases is not None:
            return self._execute_cases(ctx, report, begun)
        gate = time.perf_counter() - begun
        if not report.products:
            return self._execute_product(ctx, report, gate)
        results = []
        for code, child in report.products.items():
            product_ctx = replace(
                ctx,
                config=child.config,
                diagnostics=ctx.diagnostics / code if ctx.diagnostics is not None else None,
            )
            results.append(self._execute_product(product_ctx, child, 0.0))
        return RunResult(
            self.name,
            tuple(path for result in results for path in result.files),
            {code: identity for result in results for code, identity in result.kernels.items()},
            {
                "gate": gate,
                **{
                    f"{code}.{name}": seconds
                    for code, result in zip(report.products, results, strict=True)
                    for name, seconds in result.timings.items()
                },
            },
            tuple(dict.fromkeys(note for result in results for note in result.notes)),
            ctx.diagnostics,
            cache_hits={code: hit for result in results for code, hit in result.cache_hits.items()},
        )

    def _execute_cases(self, ctx: RunContext, report: CheckReport, begun: float) -> RunResult:
        products = report.products or {ctx.config.products_to_run[0]: report}
        # check has resolved and validated every case before compiling or writing outputs.
        cases = report.cases
        kernels = {
            code: product_kernel(run_factory(child.config).definition(), device=child.config.device)
            for code, child in products.items()
        }
        files: list[Path] = []
        rows: list[dict[str, object]] = []
        results: list[RunResult] = []
        baselines: dict[str, dict[str, float]] = {}
        for case in (None, *cases):
            name = case.name if case is not None else BASE
            for code in products:
                checked_case = report.case_reports[name] if case is not None else report
                inputs = checked_case.products[code] if checked_case.products else checked_case
                destination = ctx.output / name if case is not None else ctx.output
                diagnostics = ctx.diagnostics
                if diagnostics is not None:
                    diagnostics = diagnostics / name / code
                product_ctx = replace(
                    ctx, config=inputs.config, output=destination, diagnostics=diagnostics
                )
                result = self._execute_product(
                    product_ctx,
                    inputs,
                    0.0,
                    case_name=name,
                    kernel=kernels[code],
                    parameters=case_parameters(
                        case,
                        inputs.config.projection_term * 12,
                        dynamic_lapse=inputs.config.dynamic_lapse,
                    ),
                )
                results.append(result)
                files.extend(result.files)
                aggregate = next(
                    path
                    for path in result.files
                    if path.name.startswith(f"{code}_{name}_aggregate_output")
                )
                added, values = impact_rows(aggregate, code, name, baselines.get(code))
                rows.extend(added)
                if case is None:
                    baselines[code] = values
        impact = ctx.output / "cases_impact.csv"
        pl.DataFrame(rows).write_csv(impact)
        files.append(impact)
        return RunResult(
            self.name,
            tuple(files),
            {code: kernel.identity for code, kernel in kernels.items()},
            {"total": time.perf_counter() - begun},
            tuple(dict.fromkeys(note for result in results for note in result.notes)),
            ctx.diagnostics,
            cache_hits={code: kernel.cache_hit for code, kernel in kernels.items()},
        )

    def _execute_product(
        self,
        ctx: RunContext,
        report: CheckReport,
        gate: float,
        *,
        case_name: str = BASE,
        kernel: Kernel | None = None,
        parameters: Mapping[str, float | npt.NDArray[np.float64]] | None = None,
    ) -> RunResult:
        cfg = ctx.config
        begun = time.perf_counter()
        factory = run_factory(cfg)
        timings: dict[str, float] = {"gate": gate}
        assert report.points is not None and report.scenarios is not None
        months = cfg.projection_term * 12
        # The run type's own parameters, then the case's (the base's are neutral).
        run_parameters = {
            **self.parameters,
            **(parameters or case_parameters(None, months, dynamic_lapse=cfg.dynamic_lapse)),
        }
        if ctx.diagnostics is not None and case_name != BASE:
            # A case shares the base's input dumps; it adds what it changes.
            _write_dumps(
                ctx.diagnostics,
                {
                    **report.dumps,
                    "case_parameters": pl.DataFrame(
                        {
                            "Projection_Step": np.arange(months),
                            **{
                                name: np.broadcast_to(np.asarray(value, np.float64), (months,))
                                for name, value in sorted(run_parameters.items())
                            },
                        }
                    ),
                    "scenarios": pl.DataFrame(
                        {name: values[0] for name, values in report.scenarios.variables.items()}
                    ),
                },
            )
        kernel = kernel or product_kernel(factory.definition(), device=cfg.device)
        timings["compile"] = kernel.compile_seconds
        first_points = (
            ModelPoints(report.points.frame.head(BLOCK), report.points.fields)
            if report.streamed_policies
            else report.points
        )
        inputs = lower(report.contexts, first_points, report.scenarios, kernel, run_parameters)
        # A supplied scenario set (anything but the one deterministic path) is written with a
        # leading Scenario column.
        scenarios = (
            None if report.scenarios.measure == "deterministic" else tuple(report.scenarios.ids)
        )
        if scenarios is None and inputs.paths != 1:
            raise ConfigError("A deterministic Valuation projects one scenario path")
        month = cfg.valuation_date.month
        calendar = (month - 1 + np.arange(inputs.months)) % 12 + 1

        schema: OutputSchema = factory.valuation_output_schema(cfg.run_type, report.points.frame)
        entries = {
            output: _label(kernel, column, basis) for output, column, basis in schema.entries
        }
        keyed = {
            output: _label(kernel, column, basis)
            for output, column, basis in schema.keys
            if column not in (POLICY, STEP, CALENDAR)
        }
        sliced = {
            output: (_label(kernel, column, basis), step)
            for output, column, basis, step in schema.seriatim
        }
        detail = cfg.output_seriatim_cf_flag == 1
        rows = tuple(dict.fromkeys((*keyed.values(), *entries.values()))) if detail else ()
        ratios = factory.aggregate_ratios(schema)
        ratio_labels = {
            output: (_label(kernel, num, basis), _label(kernel, den, basis), sign)
            for output, (num, den, basis, sign) in ratios.items()
        }
        aggregate_labels = tuple(
            dict.fromkeys(
                (
                    *entries.values(),
                    *(label for num, den, _ in ratio_labels.values() for label in (num, den)),
                )
            )
        )
        request = OutputRequest(
            aggregate=aggregate_labels,
            slices=tuple(sliced.values()),
            grids=rows,
            diagnostics=ctx.diagnostics is not None,
            batch_size=batch_size(cfg),
        )
        sink = CsvSink(ctx.output)
        numbers = report.points.frame["Policy_Number"]
        if not report.streamed_policies:
            numbers = numbers.cast(pl.String)
        recorder = (
            factory.diagnostics().projection_recorder(numbers.cast(pl.String), batch_size(cfg))
            if ctx.diagnostics is not None
            else None
        )
        files: list[Path] = []
        started = time.perf_counter()
        with ExitStack() as stack:
            stream: CsvStream | None = None
            if detail:
                name = file_name(factory.code, case_name, "output")
                stream = stack.enter_context(sink.open_stream(name))
                files.append(sink.path(name))
            first = scenarios is None  # the deterministic path has index 0

            def on_batch(batch: Batch) -> None:
                if stream is not None:
                    grid = {
                        label: batch.grids[0, g] if first else batch.grids[:, g]
                        for g, label in enumerate(batch.columns)
                    }
                    write_per_policy_month(
                        stream,
                        schema,
                        numbers[batch.start : batch.stop],
                        {output: grid[label] for output, label in {**keyed, **entries}.items()},
                        calendar=calendar,
                        scenarios=scenarios,
                    )
                if recorder is not None:
                    recorder.add(batch)

            timings["overhead"] = time.perf_counter() - begun + gate
            if report.streamed_policies:
                # Continue the executor total in logical block order across physical batches.
                # Spill per-policy slices; aggregate/field scratch never scales with the book.
                policies = report.points.frame.height
                scratch = stack.enter_context(tempfile.TemporaryFile())
                shape = (inputs.paths, len(request.slices), policies)
                slices: npt.NDArray[np.float64]
                if len(request.slices):
                    scratch.truncate(int(np.prod(shape)) * 8)
                    slices = np.memmap(scratch, mode="r+", dtype=np.float64, shape=shape)
                    mapping = getattr(slices, "_mmap", None)
                    assert mapping is not None
                    stack.callback(mapping.close)
                else:
                    slices = np.empty(shape)
                total = np.zeros((inputs.paths, len(request.aggregate), inputs.months))
                pending: list[npt.NDArray[np.float64]] = []
                pending_start = 0
                size = max(BLOCK, cfg.batch_size // BLOCK * BLOCK)
                for lo in range(0, policies, size):
                    hi = min(policies, lo + size)
                    points = ModelPoints(
                        report.points.frame.slice(lo, hi - lo), report.points.fields
                    )
                    block_inputs = lower(
                        report.contexts, points, report.scenarios, kernel, run_parameters
                    )

                    def on_block(batch: Batch, offset: int = lo) -> None:
                        nonlocal pending_start
                        cursor = 0
                        while cursor < batch.stop - batch.start:
                            start = offset + batch.start + cursor
                            take = min(
                                batch.stop - batch.start - cursor,
                                cfg.batch_size - start % cfg.batch_size,
                            )
                            pending.append(batch.grids[:, :, cursor : cursor + take])
                            cursor += take
                            stop = start + take
                            if stop == policies or stop % cfg.batch_size == 0:
                                on_batch(
                                    Batch(
                                        pending_start,
                                        stop,
                                        batch.columns,
                                        np.concatenate(pending, axis=2),
                                    )
                                )
                                pending.clear()
                                pending_start = stop

                    block = project(
                        kernel, block_inputs, request, on_batch=on_block, aggregate=total
                    )
                    slices[:, :, lo:hi] = block.slices
                    if isinstance(slices, np.memmap):
                        slices.flush()
                        mapping = getattr(slices, "_mmap", None)
                        advice = getattr(mmap, "MADV_DONTNEED", None)
                        if mapping is not None and advice is not None:
                            mapping.madvise(advice)
                    report.release_prepared_pages()
                projection = Projection(total, slices)
            else:
                projection = project(kernel, inputs, request, on_batch=on_batch)
            timings["project"] = time.perf_counter() - started
            aggregate = {
                output: projection.aggregate[0, aggregate_labels.index(label)]
                if first
                else projection.aggregate[:, aggregate_labels.index(label)]
                for output, label in entries.items()
            }
            for output, (num, den, sign) in ratio_labels.items():
                numerator = projection.aggregate[:, aggregate_labels.index(num)]
                denominator = projection.aggregate[:, aggregate_labels.index(den)]
                with np.errstate(divide="ignore", invalid="ignore"):
                    value = sign * numerator / denominator
                aggregate[output] = value[0] if first else value
            name = file_name(factory.code, case_name, "aggregate_output")
            files.append(write_aggregate(sink, name, schema, aggregate, scenarios=scenarios))
            if (summary := cfg.scenario_summary) is not None:
                columns = {
                    output: summarize(
                        values,
                        report.scenarios.weights,
                        summary.percentiles,
                        summary.cte_levels,
                        summary.tail,
                    )
                    for output, values in aggregate.items()
                }
                statistics = (
                    "Mean",
                    *(f"P_{level}" for level in summary.percentiles),
                    *(f"CTE_{level}" for level in summary.cte_levels),
                )
                name = file_name(factory.code, case_name, "scenario_summary")
                files.append(write_scenario_summary(sink, name, schema, columns, statistics))
            if sliced:
                values = {
                    output: projection.slices[0, k] if first else projection.slices[:, k]
                    for k, output in enumerate(sliced)
                }
                name = file_name(factory.code, case_name, "seriatim_output")
                files.append(
                    write_seriatim(
                        sink,
                        name,
                        schema,
                        numbers,
                        values,
                        scenarios=scenarios,
                        batch_size=cfg.batch_size if report.streamed_policies else None,
                    )
                )
            if ctx.diagnostics is not None and recorder is not None:
                _write_dumps(ctx.diagnostics, recorder.dumps())
            return RunResult(
                self.name,
                tuple(files),
                {factory.code: kernel.identity},
                timings,
                tuple(report.notes),
                ctx.diagnostics,
                cache_hits={factory.code: kernel.cache_hit},
            )


class Sensitivities(Valuation):
    """Named cases through the same valuation orchestration and product kernels; unlike
    `Valuation`, it requires `Cases` (checked with the cases, before any output)."""

    name = "Sensitivities"
