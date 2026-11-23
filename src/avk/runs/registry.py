"""Run types by name, including company entry points (`avk.run_types`), and `run`."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import replace
from importlib.metadata import entry_points
from pathlib import Path
from types import MappingProxyType
from typing import Any

from avk.runs.config import RunConfig, load_run_config
from avk.runs.context import RunContext, RunResult
from avk.runtime.errors import ConfigError
from avk.runtime.progress import ACTIVE, Audit, fingerprint


class RunType(ABC):
    """One run type: stateless, it reads its context and returns new results.

    `parameters` are the run parameters it sets: the run-time differences between run types
    inside a projection (formulas read them with `run_param(...)`), so every run type shares a
    product's kernels.
    """

    name: str
    parameters: Mapping[str, float] = MappingProxyType({})

    @abstractmethod
    def execute(self, ctx: RunContext) -> RunResult: ...


class RunTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, RunType] = {}

    def register(self, run_type: RunType) -> None:
        if not isinstance(run_type, RunType) or not getattr(run_type, "name", None):
            raise ConfigError("A run type must provide a nonempty name")
        if run_type.name in self._types:
            raise ConfigError(f"Duplicate run type: {run_type.name}")
        self._types[run_type.name] = run_type

    def for_name(self, name: str) -> RunType:
        try:
            return self._types[name]
        except KeyError as exc:
            raise ConfigError(f"Run type {name} is not registered") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._types))

    @classmethod
    def default(cls) -> "RunTypeRegistry":
        from avk.runs.ifrs17 import IFRS17
        from avk.runs.stress_capital import StressCapital
        from avk.runs.valuation import Sensitivities, Valuation

        registry = cls()
        registry.register(Valuation())
        registry.register(Sensitivities())
        registry.register(StressCapital())
        registry.register(IFRS17())
        for entry in entry_points(group="avk.run_types"):
            try:
                loaded = entry.load()
                registry.register(loaded() if isinstance(loaded, type) else loaded)
            except Exception as exc:
                raise ConfigError(f"Cannot load run type entry point {entry.name}: {exc}") from exc
        return registry


def _record_config_failure(
    path: str | Path,
    root: str | Path | None,
    output: str | Path | None,
    diagnostics: str | Path | None,
    error: ConfigError,
) -> None:
    """Preserve bad-settings evidence wherever an output folder can be identified."""
    import hashlib
    import json

    import yaml  # type: ignore[import-untyped]

    path = Path(path).resolve()
    try:
        content = path.read_bytes()
    except OSError:
        content = None
    try:
        text = content.decode("utf-8-sig") if content is not None else ""
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError):
        data = None
    data = data if isinstance(data, dict) else {}
    destination = output if output is not None else data.get("Output_path", data.get("output_path"))
    if not isinstance(destination, (str, Path)):
        return
    try:
        try:
            base = Path(root or data.get("root_folder") or Path.cwd()).resolve()
        except (TypeError, ValueError, OSError):
            base = None
        requested = Path(destination)
        if not requested.is_absolute() and base is None:
            return
        if requested.is_absolute():
            folder = requested.resolve()
        else:
            assert base is not None
            folder = (base / requested).resolve()
        audit = Audit(folder, json.loads(json.dumps(data, default=str)), None)
        try:
            audit.record.update(
                resolved_root=str(base) if base is not None else None,
                output_path=str(folder),
                diagnostics_path=str(Path(diagnostics).resolve())
                if diagnostics is not None
                else None,
            )
            audit.record["inputs"][str(path)] = {
                "path": str(path),
                "sha256": hashlib.sha256(content).hexdigest() if content is not None else None,
            }
            if content is None:
                audit.record["inputs"][str(path)]["error"] = "configuration unreadable"
            audit.finish(error=error)
        finally:
            audit.close()
    except (OSError, ValueError, TypeError):
        # Preserve the original strict error if the output cannot host an audit.
        return


def run(
    config: str | Path | RunConfig,
    *,
    root: str | Path | None = None,
    progress: Any = None,
    diagnostics: str | Path | None = None,
    output: str | Path | None = None,
) -> RunResult:
    try:
        cfg = config if isinstance(config, RunConfig) else load_run_config(config)
    except ConfigError as exc:
        if not isinstance(config, RunConfig):
            _record_config_failure(config, root, output, diagnostics, exc)
        raise
    if output is not None:
        cfg = cfg.model_copy(update={"output_path": Path(output).resolve()})
    base_root = Path(root or cfg.root_folder or Path.cwd()).resolve()
    context = RunContext(
        cfg,
        base_root,
        (base_root / cfg.output_path).resolve(),
        Path(diagnostics).resolve() if diagnostics is not None else None,
        progress,
    )
    audit = Audit(context.output, cfg.model_dump(mode="json", by_alias=True), progress)
    token = ACTIVE.set(audit)
    logger = logging.getLogger("avk")
    logger.addHandler(audit)
    try:
        audit.record.update(
            resolved_root=str(base_root),
            output_path=str(context.output),
            diagnostics_path=str(context.diagnostics) if context.diagnostics is not None else None,
        )
        audit.status("validating")
        if cfg._path is not None:
            fingerprint(cfg._path)
        result = RunTypeRegistry.default().for_name(cfg.run_type).execute(context)
        result = replace(
            result,
            notes=tuple(
                dict.fromkeys(
                    (
                        *result.notes,
                        *audit.record.get("product_summaries", ()),
                    )
                )
            ),
        )
        audit.finish(result=result)
        return result
    except BaseException as exc:
        audit.finish(error=exc)
        raise
    finally:
        logger.removeHandler(audit)
        ACTIVE.reset(token)
        audit.close()
