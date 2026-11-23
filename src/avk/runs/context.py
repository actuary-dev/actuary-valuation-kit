"""What a run type receives and returns. Both are frozen; nothing persists between runs."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from avk.runs.config import RunConfig


@dataclass(frozen=True)
class RunContext:
    config: RunConfig
    root: Path  # resolved base folder for relative inputs and outputs
    output: Path  # resolved output folder
    diagnostics: Path | None = None  # native columns of every policy-month, for debugging
    progress: Any = None  # optional progress observer


@dataclass(frozen=True)
class RunResult:
    run_type: str
    files: tuple[Path, ...]  # output files written, in writing order
    kernels: Mapping[str, str] = field(default_factory=dict)  # product code -> kernel identity
    timings: Mapping[str, float] = field(default_factory=dict)  # seconds, by step
    notes: tuple[str, ...] = ()
    diagnostics: Path | None = None
    cache_hits: Mapping[str, bool] = field(default_factory=dict)  # product code -> loaded

    def __post_init__(self) -> None:
        for name in ("kernels", "timings", "cache_hits"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def manifest(self) -> dict[str, Any]:
        """Kernel identities included in the run audit."""
        return {"kernel_identities": dict(self.kernels)}
