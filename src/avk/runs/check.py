"""Shared pre-flight orchestration: definitions, contexts, model points and scenarios.

Product-generic: everything product-specific comes through the `ProductFactory` contract.
"""

import json
import logging
import mmap
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

from avk.assumptions.context import (
    AssumptionContext,
    AssumptionSpec,
    ScenarioVariable,
    build_context,
    load_declared,
)
from avk.assumptions.models import InterestCurveAssumption, ProductParameters, TabularAssumption
from avk.esg import registry as generators
from avk.inputs.registry import InputSpec
from avk.inputs.sources import ResolvedInputs, Sources
from avk.inputs.validation import Issue
from avk.model.compiler import bound
from avk.model.data import ModelPoints, ScenarioSet, Table
from avk.model.manifest import Manifest
from avk.products.registry import ProductFactory, ProductRegistry
from avk.runs.batching import group_by_code
from avk.runs.compile import product_ir
from avk.runs.config import RunConfig, load_run_config
from avk.runtime.errors import AvkError, ConfigError, InputError, OutputError
from avk.runtime.progress import checked

if TYPE_CHECKING:
    from avk.runs.capital_settings import CapitalSettings
    from avk.runs.cases import Case
    from avk.runs.ifrs17_settings import MeasurementSettings
    from avk.runs.stresses import Stress


@dataclass
class CheckReport:
    config: RunConfig
    inputs: ResolvedInputs
    tables: dict[str, Table] = field(default_factory=dict)
    assumptions: dict[str, TabularAssumption] = field(default_factory=dict)
    dumps: dict[str, pl.DataFrame] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    contexts: dict[str, AssumptionContext] = field(default_factory=dict)
    points: ModelPoints[pl.DataFrame] | None = None
    scenarios: ScenarioSet | None = None
    products: dict[str, "CheckReport"] = field(default_factory=dict)
    cases: tuple["Case", ...] = ()  # the run's named cases, parsed and validated once
    case_reports: dict[str, "CheckReport"] = field(default_factory=dict)
    stresses: tuple["Stress", ...] = ()
    capital_settings: "CapitalSettings | None" = None
    measurement: "MeasurementSettings | None" = None
    rollforward_balances: pl.DataFrame | None = None
    streamed_policies: bool = False
    # Companion policy tables, read once per run (`ProductFactory.companion_tables`).
    companions: dict[str, pl.DataFrame] = field(default_factory=dict)
    prepared_mapping: mmap.mmap | None = field(default=None, repr=False)

    def release_prepared_pages(self) -> None:
        """Release clean prepared pages on platforms supporting mmap advice."""
        advice = getattr(mmap, "MADV_DONTNEED", None)
        if (
            self.prepared_mapping is not None
            and advice is not None
            and hasattr(self.prepared_mapping, "madvise")
        ):
            self.prepared_mapping.madvise(advice)

    @property
    def product_summaries(self) -> tuple[str, ...]:
        products = self.products or {self.config.products_to_run[0]: self}
        summaries = []
        for code, child in products.items():
            assert child.points is not None and child.scenarios is not None
            summaries.append(
                f"{code}: {child.points.frame.height} policies; "
                f"{len(child.tables)} tables; "
                f"bases {', '.join(child.contexts)}; "
                f"{child.config.projection_term * 12} months; "
                f"{len(child.scenarios.ids)} scenarios"
            )
        return tuple(summaries)

    @property
    def ok(self) -> bool:
        return True  # validation failures raise before a report is returned


def run_factory(cfg: RunConfig) -> ProductFactory:
    if len(cfg.products_to_run) != 1:
        raise ConfigError("Preparation currently supports one product per run")
    if cfg.run_type == "IFRS17":
        from avk.products.credit_life.factory import IfrsCreditLifeFactory
        from avk.products.rider.factory import (
            IfrsAccidentalDeathFactory,
            IfrsCriticalIllnessFactory,
            IfrsDisabilityFactory,
        )
        from avk.products.term.factory import IfrsTermFactory

        factories: dict[str, type[ProductFactory]] = {
            "TERM": IfrsTermFactory,
            "ACCIDENTAL_DEATH_RIDER": IfrsAccidentalDeathFactory,
            "CRITICAL_ILLNESS_RIDER": IfrsCriticalIllnessFactory,
            "DISABILITY_RIDER": IfrsDisabilityFactory,
            "CREDIT_LIFE": IfrsCreditLifeFactory,
        }
        if cfg.products_to_run[0] in factories:
            return factories[cfg.products_to_run[0]]()
    return ProductRegistry.default().for_code(cfg.products_to_run[0])


def _resolve_inputs(cfg: RunConfig, base_root: Path) -> ResolvedInputs:
    if cfg.inputs is None:
        raise ConfigError("Inputs is required. Set Inputs.Tables to the table list.")
    return Sources.resolve(cfg.inputs, base=cfg._path.parent if cfg._path else base_root)


def _scenario_variables(cfg: RunConfig, spec: AssumptionSpec) -> tuple[ScenarioVariable, ...]:
    return tuple(
        replace(variable, fiscal_start_month=cfg.fiscal_start_month)
        if variable.fiscal_start_month == "fiscal_start_month"
        else variable
        for variable in spec.scenario_variables
    )


def _scenario_curves(
    spec: AssumptionSpec, assumptions: dict[str, TabularAssumption]
) -> dict[str, InterestCurveAssumption]:
    curves: dict[str, InterestCurveAssumption] = {}
    for name in sorted({variable.curve for variable in spec.scenario_variables}):
        curve = assumptions.get(name)
        if not isinstance(curve, InterestCurveAssumption):
            raise ConfigError(f"{spec.product}: {name} is not an interest curve")
        curves[name] = curve
    return curves


def _check_declarations(code: str, spec: AssumptionSpec, declared: Manifest) -> None:
    """The loading specification covers exactly what the definition binds."""
    tables = declared.tables | declared.curves
    unused = set(spec.tables) - tables
    if unused:
        raise ConfigError(f"{code}: assumption specification for unbound tables {sorted(unused)}")
    missing = tables - set(spec.tables)
    if missing:
        raise ConfigError(f"{code}: missing assumption specification {sorted(missing)}")
    generated = {variable.name for variable in spec.scenario_variables}
    if declared.scen_vars != generated:
        raise ConfigError(
            f"{code}: scenario variables bound {sorted(declared.scen_vars)} "
            f"but declared {sorted(generated)}"
        )


def _companions(
    factory: ProductFactory, inputs: ResolvedInputs, report: CheckReport
) -> dict[str, pl.DataFrame]:
    """The factory's companion policy tables, each read once per run."""
    for name in factory.companion_tables:
        if name not in report.companions:
            report.companions[name] = inputs.read(name)
    return {name: report.companions[name] for name in factory.companion_tables}


def _raise_errors(issues: list[Issue], report: CheckReport) -> None:
    report.notes.extend(issue.message for issue in issues if issue.severity == "warning")
    errors = [issue.message for issue in issues if issue.severity == "error"]
    if errors:
        raise InputError("\n".join(errors))


def _prepare(
    factory: ProductFactory,
    inputs: ResolvedInputs,
    cfg: RunConfig,
    report: CheckReport,
    raw: pl.DataFrame | None = None,
    *,
    batch: bool = False,
) -> ModelPoints[pl.DataFrame]:
    if raw is None and inputs.location(factory.policy_table).source == "parquet":
        import sqlite3

        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.ipc as ipc  # type: ignore[import-untyped]

        companions = _companions(factory, inputs, report)
        spool = inputs.temporary()
        fields: tuple[str, ...] = ()
        with spool.open("wb") as handle:
            writer = None
            schema = None
            try:
                for rows in inputs.policy_batches(factory.policy_table, cfg.batch_size):
                    prepared = _prepare(factory, inputs, cfg, report, rows, batch=True)
                    fields = prepared.fields
                    if schema is None:
                        schema = prepared.frame.schema
                        # Status is a numeric model field with NaN for missing values.
                        # Other raw columns retain the Parquet file's own fixed schema;
                        # the adapters declare the remaining derived column types.
                        if "Policy_Status" in schema:
                            schema["Policy_Status"] = pl.Float64()
                    table = prepared.frame.cast(schema).to_arrow(
                        compat_level=pl.CompatLevel.newest()
                    )
                    if writer is None:
                        writer = ipc.new_file(handle, table.schema)
                    writer.write_table(table)
            finally:
                if writer is not None:
                    writer.close()
        if writer is None:
            raise InputError(f"{factory.policy_table}: has no policies")
        # An exact on-disk index bounds duplicate-check scratch independently of the
        # book. Arrow reads one record batch, never a whole identifier column.
        index = spool.with_suffix(".sqlite")
        orphans: list[Issue] = []
        try:
            with closing(sqlite3.connect(index)) as connection:
                connection.execute("PRAGMA cache_size=-2048")
                connection.execute("CREATE TABLE ids (value PRIMARY KEY) WITHOUT ROWID")
                # Close the spool explicitly: Arrow's reader keeps a path-opened file
                # open after its block, and Windows cannot remove an open file.
                with pa.OSFile(str(spool), "rb") as source, ipc.open_file(source) as reader:
                    column = reader.schema.get_field_index("Policy_Number")
                    for i in range(reader.num_record_batches):
                        identifiers = reader.get_batch(i).column(column).to_pylist()
                        connection.executemany("INSERT INTO ids VALUES (?)", zip(identifiers))
                if companions:
                    assert schema is not None
                    dtype = schema["Policy_Number"]

                    def known(values: pl.Series) -> pl.Series:
                        """Policy numbers present in the streamed book (index lookups)."""
                        probe = values.cast(dtype, strict=False)
                        candidates = probe.drop_nulls().unique().to_list()
                        found: list[Any] = []
                        for start in range(0, len(candidates), 900):
                            chunk = candidates[start : start + 900]
                            marks = ",".join("?" * len(chunk))
                            found.extend(
                                row[0]
                                for row in connection.execute(
                                    f"SELECT value FROM ids WHERE value IN ({marks})", chunk
                                )
                            )
                        return probe.is_in(pl.Series(found, dtype=dtype).implode()).fill_null(False)

                    orphans = factory.validator().companion_orphans(known, companions)
        except sqlite3.IntegrityError as exc:
            raise InputError(
                f"{factory.policy_table}: duplicate value(s) in identifier column"
            ) from exc
        finally:
            index.unlink(missing_ok=True)
        _raise_errors(orphans, report)
        report.streamed_policies = True
        report.notes[:] = list(dict.fromkeys(report.notes))
        # Own the mapping so clean pages can be discarded after each physical batch.
        # Arrow view types and no rechunking retain zero-copy prepared columns.
        mapping = inputs.map_prepared(spool)
        report.prepared_mapping = mapping
        with ipc.open_file(pa.BufferReader(mapping)) as reader:
            frame = pl.from_arrow(reader.read_all(), rechunk=False)
        assert isinstance(frame, pl.DataFrame)
        report.release_prepared_pages()
        return ModelPoints(frame, fields)
    raw = inputs.read(factory.policy_table) if raw is None else raw
    issues = factory.validator().validate_at(raw, cfg.valuation_date)
    errors = [issue.message for issue in issues if issue.severity == "error"]
    report.notes.extend(issue.message for issue in issues if issue.severity == "warning")
    if errors:
        # Keep validation messages and report any row for an unrequested product.
        try:
            codes = factory.model_point_adapter({}).product_codes(raw)
            if codes.is_null().any() or (~codes.is_in(cfg.products_to_run)).any():
                errors.append(f"{factory.policy_table}: product code not in Products_to_run")
        except pl.exceptions.PolarsError:
            errors.append(f"{factory.policy_table}: product code not in Products_to_run")
        raise InputError("\n".join(errors))
    tables = MappingProxyType(dict(report.tables))
    companions = _companions(factory, inputs, report)
    if companions:
        validator = factory.validator()
        _raise_errors(validator.validate_companions(raw, companions, cfg.valuation_date), report)
        adapter = factory.companion_adapter(tables, MappingProxyType(companions))
    else:
        adapter = factory.model_point_adapter(tables)
    try:
        points = adapter.prepare(raw, cfg)
    except pl.exceptions.PolarsError as exc:
        raise InputError(f"{factory.policy_table}: cannot prepare model points: {exc}") from exc
    if companions and not batch:
        numbers = points.frame["Policy_Number"]

        def known(values: pl.Series) -> pl.Series:
            """Policy numbers present in the book."""
            return (
                values.cast(numbers.dtype, strict=False).is_in(numbers.implode()).fill_null(False)
            )

        _raise_errors(validator.companion_orphans(known, companions), report)
    return points


def _check_single(
    config: str | Path | RunConfig,
    *,
    root: str | Path | None = None,
    dump_inputs: str | Path | None = None,
    inputs: ResolvedInputs | None = None,
    raw: pl.DataFrame | None = None,
    defer_dumps: bool = False,
    shared: CheckReport | None = None,
) -> CheckReport:
    cfg = config if isinstance(config, RunConfig) else load_run_config(config)
    base_root = Path(root or cfg.root_folder or Path.cwd()).resolve()
    factory = run_factory(cfg)
    inputs = _resolve_inputs(cfg, base_root) if inputs is None else inputs
    diagnostics = factory.diagnostics()
    report = CheckReport(cfg, inputs)
    months = cfg.projection_term * 12

    # The formulas are checked first: a definition error is reported with its file and line
    # before anything reads the definition's bindings or any input.
    ir = product_ir(factory.definition())
    spec = factory.assumption_spec()
    if shared is not None:
        for name, assumption in shared.assumptions.items():
            logical = spec.tables[name].logical_name
            if (
                logical in inputs.fingerprints
                and inputs.fingerprints[logical] == shared.inputs.fingerprints.get(logical)
                and (
                    not isinstance(assumption, InterestCurveAssumption)
                    or cfg.valuation_date == shared.config.valuation_date
                )
            ):
                spec.cache[name] = assumption
    # Strict parameters first retains the existing failure order and diagnostics.
    spec.scenario_variables = _scenario_variables(cfg, spec)
    parameters = spec.load_parameters(inputs)
    # The input gate validates everything the definition declares (bound); each basis
    # context then holds exactly what that basis's formulas reach (the IR's manifest).
    declared = bound(ir)
    _check_declarations(factory.code, spec, declared)
    assumptions = load_declared(spec, inputs, cfg)
    report.assumptions = assumptions
    for name in sorted(declared.params):
        parameters.require(name)
    # The generator reads the interest curves its scenario variables name; schedule curves are
    # read by formulas instead.
    curves = _scenario_curves(spec, assumptions)
    for basis in ir.bases:
        context = build_context(spec, ir.manifest[basis], basis, inputs, cfg)
        old = shared.contexts[basis] if shared is not None else None
        report.contexts[basis] = (
            old
            if old is not None
            and old.valuation_date == cfg.valuation_date
            and old.params == context.params
            and old.source_hashes == context.source_hashes
            and all(old.tables[name] is item for name, item in context.tables.items())
            and all(old.curves[name] is item for name, item in context.curves.items())
            else context
        )
    report.tables.update({name: item.table for name, item in assumptions.items()})
    report.tables["product_parameters"] = (
        shared.tables["product_parameters"]
        if shared is not None
        and inputs.fingerprints["product_parameters"]
        == shared.inputs.fingerprints["product_parameters"]
        else ProductParameters.load_table(inputs, spec.parameter_column or spec.product, months)
    )

    report.points = _prepare(factory, inputs, cfg, report, raw)

    location = cfg.inputs.scenarios if cfg.inputs else None
    if location is None:
        report.notes.append(f"Inputs.Scenarios absent: using {generators.DEFAULT}")
    run_folder = cfg._path.parent if cfg._path else base_root
    generator = generators.generator_for(location, spec.scenario_variables, base=run_folder)
    report.scenarios = (
        shared.scenarios
        if shared is not None
        and shared.scenarios is not None
        and cfg.valuation_date == shared.config.valuation_date
        and cfg.fiscal_start_month == shared.config.fiscal_start_month
        and all(shared.assumptions[name] is curve for name, curve in curves.items())
        else generator.generate(curves, months)
    )
    if cfg.scenario_summary is not None and len(report.scenarios.ids) < 2:
        raise ConfigError("Scenario_Summary requires multiple scenario paths")

    if dump_inputs is not None:
        report.dumps = diagnostics.assumption_dumps(assumptions, parameters, inputs, cfg)
        for name in report.points.fields:
            report.dumps[f"inforce__{name}"] = pl.DataFrame(
                {
                    "Policy_Number": report.points.frame["Policy_Number"],
                    name: report.points.frame[name],
                }
            )
        report.dumps["prepared_policies"] = report.points.frame
        report.dumps["scenarios"] = pl.DataFrame(
            {name: values[0] for name, values in report.scenarios.variables.items()}
        )
        report.dumps.update(
            diagnostics.preparation_dumps(report.points, report.scenarios, cfg, cfg.batch_size)
        )
    for note in report.notes:
        logging.getLogger(__name__).info(note)
    if dump_inputs is not None and not defer_dumps:
        _write_dumps(report, Path(dump_inputs), base_root, parameters)
    return report


def _check_base(
    config: str | Path | RunConfig,
    *,
    root: str | Path | None = None,
    dump_inputs: str | Path | None = None,
    inputs: ResolvedInputs | None = None,
    shared: CheckReport | None = None,
) -> CheckReport:
    """Validate all requested product groups before any projection."""
    cfg = config if isinstance(config, RunConfig) else load_run_config(config)
    base_root = Path(root or cfg.root_folder or Path.cwd()).resolve()
    if len(cfg.products_to_run) == 1:
        return _check_single(cfg, root=root, dump_inputs=dump_inputs, inputs=inputs, shared=shared)
    inputs = _resolve_inputs(cfg, base_root) if inputs is None else inputs
    registry = ProductRegistry.default()
    factories = [registry.for_code(code) for code in cfg.products_to_run]
    collected: dict[str, list[pl.DataFrame]] = {code: [] for code in cfg.products_to_run}
    seen: set[tuple[str, str | None]] = set()
    for factory in factories:
        location = inputs.location(factory.policy_table)
        key = (location.source, location.path)
        if key in seen:
            continue
        seen.add(key)
        raw = inputs.read(factory.policy_table)
        adapter = factory.model_point_adapter({})
        try:
            codes = adapter.product_codes(raw)
        except pl.exceptions.PolarsError as exc:
            raise InputError(
                f"{factory.policy_table}: product code not in Products_to_run; "
                f"cannot derive product code: {exc}"
            ) from exc
        if codes.is_null().any() or (~codes.is_in(cfg.products_to_run)).any():
            raise InputError(f"{factory.policy_table}: product code not in Products_to_run")
        points = ModelPoints(raw.with_columns(codes.alias("Product_Code")), ())
        for code in group_by_code(points):
            # Keep original labels so validation can check that the option matches the product.
            collected[code].append(raw.filter(codes == code))
    report = CheckReport(cfg, inputs)
    for factory in factories:
        frames = collected[factory.code]
        if not frames:
            raise InputError(f"{factory.code}: has no policies")
        # Optional product labels can be omitted per source. Fill only absent columns
        # with the adapter-derived code; validation rejects wrong or null labels.
        labels = {"Product Code", "Product_Code"} & set().union(
            *(frame.columns for frame in frames)
        )
        aligned = [
            frame.with_columns(
                pl.lit(factory.code).alias(name) for name in labels - set(frame.columns)
            )
            for frame in frames
        ]
        try:
            raw = pl.concat(aligned, how="diagonal_relaxed")
        except pl.exceptions.PolarsError as exc:
            raise InputError(f"{factory.code}: incompatible policy sources: {exc}") from exc
        child = _check_single(
            cfg.model_copy(update={"products_to_run": (factory.code,)}),
            root=base_root,
            dump_inputs=Path(dump_inputs) / factory.code if dump_inputs is not None else None,
            inputs=inputs,
            raw=raw,
            defer_dumps=True,
            shared=shared.products.get(factory.code) if shared is not None else None,
        )
        report.products[factory.code] = child
        report.notes.extend(child.notes)
    if dump_inputs is not None:
        for factory in factories:
            child = report.products[factory.code]
            parameters = factory.assumption_spec().load_parameters(inputs)
            _write_dumps(child, Path(dump_inputs) / factory.code, base_root, parameters)
    return report


def check(
    config: str | Path | RunConfig,
    *,
    root: str | Path | None = None,
    dump_inputs: str | Path | None = None,
) -> CheckReport:
    """The same complete input gate for ordinary runs and every independent case."""
    from avk.runs.cases import case_report, load_cases
    from avk.runs.ifrs17_rollforward_settings import configure_rollforward
    from avk.runs.overrides import resolve_overrides
    from avk.runs.stresses import load_stresses

    cfg = config if isinstance(config, RunConfig) else load_run_config(config)
    cfg, rollforward_logical = configure_rollforward(cfg)
    base_root = Path(root or cfg.root_folder or Path.cwd()).resolve()
    cfg, stresses = load_stresses(cfg, base_root)
    cases = load_cases(cfg, base_root)
    report = _check_base(cfg, root=base_root, dump_inputs=dump_inputs)
    report.cases = cases
    report.stresses = stresses
    if cfg.run_type == "IFRS17":
        from avk.runs.ifrs17 import _capital_report
        from avk.runs.ifrs17_settings import measurement_settings

        for child in (report.products or {cfg.products_to_run[0]: report}).values():
            child.measurement = measurement_settings(child)
            _capital_report(child, base_root, scope=cfg.products_to_run)
    elif cfg.ifrs17 is not None:
        raise ConfigError("IFRS17 settings require Run_Type IFRS17")
    if stresses:
        from avk.runs.capital_settings import capital_settings, discount_curve

        assert isinstance(cfg.stress_set, dict)
        report.capital_settings = capital_settings(
            cfg.stress_set,
            tuple(s.risk for s in stresses),
            cfg._path.parent if cfg._path else base_root,
        )
        if report.capital_settings is not None:
            shared_rates = None
            for child in (report.products or {cfg.products_to_run[0]: report}).values():
                assert child.scenarios is not None
                curve = report.capital_settings.curve
                rates = discount_curve(child, curve)
                if not np.isfinite(rates).all() or (rates <= -1).any():
                    raise ConfigError("Settings.Discount_Curve must be finite and exceed -1")
                if shared_rates is not None and not np.array_equal(rates, shared_rates):
                    raise ConfigError(
                        "Combined portfolio needs identical Discount_Curve rates for every product"
                    )
                shared_rates = rates
    if cfg.cases is None:
        checked(report)
        return report
    products = report.products or {cfg.products_to_run[0]: report}
    if any(
        child.scenarios is None or child.scenarios.measure != "deterministic"
        for child in products.values()
    ):
        raise ConfigError(
            "Cases require a deterministic valuation; "
            "supplied scenarios need a defined impact reduction"
        )
    for case in cases:
        try:
            if case.overrides:
                config, inputs = resolve_overrides(report, case.overrides, base_root)
                destination = Path(dump_inputs) / case.name if dump_inputs is not None else None
                resolved = _check_base(
                    config, root=base_root, dump_inputs=destination, inputs=inputs, shared=report
                )
            else:
                resolved = report
            if resolved.products:
                prepared = replace(
                    resolved,
                    products={
                        code: case_report(child, case) for code, child in resolved.products.items()
                    },
                    cases=(),
                    case_reports={},
                )
            else:
                prepared = replace(case_report(resolved, case), cases=(), case_reports={})
            report.case_reports[case.name] = prepared
            if cfg.run_type == "IFRS17":
                for child in (prepared.products or {cfg.products_to_run[0]: prepared}).values():
                    child.measurement = measurement_settings(child)
                    _capital_report(child, base_root, case, cfg.products_to_run)
        except AvkError as exc:
            raise ConfigError(f"{case.name}: {exc}") from exc
    if stresses:
        base_products = report.products or {cfg.products_to_run[0]: report}
        for case in cases:
            resolved = report.case_reports[case.name]
            children = resolved.products or {cfg.products_to_run[0]: resolved}
            for code, child in children.items():
                base = base_products[code]
                assert child.points is not None and base.points is not None
                if not child.points.frame["Policy_Number"].equals(
                    base.points.frame["Policy_Number"]
                ):
                    raise ConfigError(
                        f"{case.name}: stress cases require the same ordered policy IDs"
                    )
    if rollforward_logical is not None:
        from avk.runs.ifrs17_rollforward_settings import check_rollforward

        report.rollforward_balances = check_rollforward(report, rollforward_logical)
    checked(report)
    return report


def _write_dumps(
    report: CheckReport, destination: Path, base_root: Path, parameters: ProductParameters
) -> None:
    cfg, inputs, scenarios = report.config, report.inputs, report.scenarios
    assert scenarios is not None
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for name, frame in report.dumps.items():
            frame.write_parquet(destination / f"{name}.parquet")
        for name, loaded in report.tables.items():
            pl.DataFrame(loaded.values).write_parquet(
                destination / f"table__{name.replace('/', '__')}.parquet"
            )
        for basis, context in report.contexts.items():
            pl.DataFrame(
                {"parameter": list(context.params), "value": list(context.params.values())},
                schema={"parameter": pl.String, "value": pl.Float64},  # typed even when empty
            ).write_parquet(destination / f"context__{basis}__params.parquet")
            for name, assumption in {**context.tables, **context.curves}.items():
                pl.DataFrame(assumption.table.values).write_parquet(
                    destination / f"context__{basis}__{name.replace('/', '__')}.parquet"
                )
        record: dict[str, Any] = {
            "configuration": cfg.model_dump(mode="json", by_alias=True),
            "resolved_root": str(base_root),
            "output_path": str((base_root / cfg.output_path).resolve()),
            "notes": report.notes,
            "parameters": dict(parameters.variables),
            "contexts": {
                basis: {
                    "tables": sorted(ctx.tables),
                    "curves": sorted(ctx.curves),
                    "params": dict(ctx.params),
                    "fields": sorted(ctx.manifest.fields),
                    "scen_vars": sorted(ctx.manifest.scen_vars),
                    "source_hashes": dict(ctx.source_hashes),
                }
                for basis, ctx in report.contexts.items()
            },
            "scenarios": {
                "ids": scenarios.ids,
                "weights": scenarios.weights.tolist(),
                "measure": scenarios.measure,
                "provenance": dict(scenarios.provenance),
            },
            "read_log": inputs.read_log,
            "inputs": {
                name: {
                    **inputs.location(name).model_dump(mode="json", by_alias=True),
                    "sha256": digest,
                }
                for name, digest in inputs.fingerprints.items()
            },
        }
        (destination / "config.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise OutputError(f"Cannot write input dump to {destination}: {exc}") from exc


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    message: str


def preflight(
    config: str | Path | RunConfig, locations: InputSpec | dict[str, Any] | None = None
) -> list[Check]:
    """Run the same gate as check, returning presentation-ready checks rather than exiting."""
    try:
        cfg = config if isinstance(config, RunConfig) else load_run_config(config)
        if locations is not None:
            inputs = (
                locations
                if isinstance(locations, InputSpec)
                else InputSpec.model_validate(locations)
            )
            cfg = cfg.model_copy(update={"inputs": inputs})
        report = check(cfg)
        return [
            Check("inputs", True, "Input preparation passed"),
            *[Check("product", True, text) for text in report.product_summaries],
            *[Check("note", True, note) for note in report.notes],
        ]
    except (AvkError, ValueError) as exc:
        return [Check("inputs", False, str(exc))]
