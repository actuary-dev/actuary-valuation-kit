"""Public library entry points; may use orchestration and runtime, never the UI."""

from collections.abc import Sequence
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

from avk.runs.check import Check as Check
from avk.runs.check import CheckReport as CheckReport
from avk.runs.check import check as check
from avk.runs.check import preflight as preflight
from avk.runs.compile import KernelInfo as KernelInfo
from avk.runs.compile import compile_products
from avk.runs.config import RunConfig as RunConfig
from avk.runs.config import load_run_config as load_run_config
from avk.runs.context import RunResult as RunResult
from avk.runs.registry import run as run_config
from avk.runs.ul_compliance import ComplianceReport as ComplianceReport
from avk.runs.ul_compliance import ul_compliance as ul_compliance
from avk.runtime.errors import AvkError as AvkError
from avk.runtime.errors import ConfigError as ConfigError
from avk.runtime.errors import FormulaError as FormulaError
from avk.runtime.errors import InputError as InputError
from avk.runtime.errors import KernelError as KernelError
from avk.runtime.errors import OutputError as OutputError


def version() -> str:
    """Return the installed version, single-sourced in pyproject.toml."""
    return distribution_version("actuary-valuation-kit")


def compile(
    codes: Sequence[str] = (),
    *,
    device: str = "cpu",
    explain: bool = False,
    listing: bool = False,
) -> list[KernelInfo]:
    """Each product (every registered code when `codes` is empty; a code may also be a path to
    a product source file): with `explain`, checked, scheduled and described; with `listing`,
    also emitted and identified without compiling; otherwise built through the disk cache in
    `AVK_CACHE_DIR`, reporting each identity and `cache_hit`."""
    return compile_products(codes, device=device, explain=explain, listing=listing)


def run(
    config: str | Path | RunConfig,
    *,
    root: str | Path | None = None,
    progress: Any = None,
    diagnostics: str | Path | None = None,
    output: str | Path | None = None,
) -> RunResult:
    """Validate, project and write one run. `diagnostics` names a folder for every column of
    every policy-month and the input dumps (a development aid for small books).
    output replaces the configured output folder, including for failed settings validation."""
    return run_config(config, root=root, progress=progress, diagnostics=diagnostics, output=output)
