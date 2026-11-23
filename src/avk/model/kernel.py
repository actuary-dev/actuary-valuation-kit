"""Kernels: a product definition compiled for one basis set and device, cached on disk.

`compile_product` builds the IR, emits one module and hashes it. The identity is the sha256 of
the generated source plus the emitter version, the Numba version and the target, so
docstrings and labels, which are never emitted, cannot change it. The module is written once
per identity to `<cache>/kernels/<code>-<identity16>/kernel.py` (one file per identity, never
rewritten, so Numba's source stamp and cache stay valid) and imported; its functions use
`cache=True`, so a later process loads the compiled drivers instead of compiling them.

Within a process a loaded kernel is reused by identity: compiling is idempotent, and nothing
about a run is kept.
"""

import contextlib
import hashlib
import importlib.util
import os
import platform
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numba
from numba import types
from numba.core.errors import NumbaError

from avk.model.cache import cache_root, numba_cache_dir
from avk.model.compiler import build_ir
from avk.model.emit import numba_cpu
from avk.model.emit.common import Layout
from avk.model.ir import ProductIR
from avk.model.lang import Product
from avk.model.manifest import Manifest

EMITTER = "avk-emitter-2"
DEVICES = ("cpu",)
_LOADED: dict[str, tuple[Callable[..., None], Callable[..., None]]] = {}


class KernelBuildError(RuntimeError):
    """Generated code that the device compiler rejects (the run layer reports `KernelError`)."""


@dataclass(frozen=True)
class Kernel:
    """Compiled functions and metadata only; nothing in it changes after compilation."""

    identity: str
    columns: tuple[str, ...]  # scratch rows: `name` or `name@basis` (see `Layout.columns`)
    manifest: Mapping[str, Manifest]  # reached requirements per basis
    ir: ProductIR
    layout: Layout
    source: str
    compile_seconds: float  # compiling, or loading from the cache
    run_aggregate: Callable[..., None]
    run_rows: Callable[..., None]
    cache_hit: bool = False  # the drivers were loaded, not compiled
    path: Path | None = None  # the generated module


@dataclass(frozen=True)
class Emitted:
    """A definition's generated kernel source and identity, before any compilation."""

    ir: ProductIR
    source: str
    layout: Layout
    identity: str


def target(device: str) -> str:
    return f"{device}-{platform.machine()}"


def emit_product(
    definition: type[Product], *, bases: tuple[str, ...], device: str = "cpu"
) -> Emitted:
    """Check, schedule and emit `definition`, and hash the source into its identity."""
    if device not in DEVICES:
        raise ValueError(f"device {device!r} is not available in this release")
    ir = build_ir(definition, bases=bases)
    source, layout = numba_cpu.emit(ir)
    identity = hashlib.sha256(
        "\n".join((source, EMITTER, numba.__version__, target(device))).encode()
    ).hexdigest()
    return Emitted(ir, source, layout, identity)


def _signatures(tables: tuple[int, ...]) -> tuple[Any, Any]:
    """The drivers' Numba signatures: C-contiguous arrays, one per table (or curve) of its
    dimension."""
    numba_array: Any = types.Array

    def array(dtype: Any, ndim: int) -> Any:
        return numba_array(dtype, ndim, "C")

    args = (
        array(types.float64, 2),
        array(types.int64, 2),
        array(types.int64, 1),
        array(types.float64, 1),
        array(types.float64, 3),
        *(array(types.float64, ndim) for ndim in tables),
        types.int64,  # M
        types.int64,  # st, the scenario tile
    )
    accumulate = (array(types.int64, 1), array(types.float64, 4))
    rows = (
        array(types.int64, 1),
        array(types.float64, 4),
        array(types.int64, 1),
        array(types.int64, 1),
        array(types.float64, 3),
    )
    head = (types.int64, types.int64)
    return (
        types.void(*head, *args, *accumulate),
        types.void(*head, *args, *accumulate, *rows),
    )


def _module_file(code: str, identity: str, source: str) -> Path:
    """The generated module's file, written once; an existing file must hold this source."""
    folder = cache_root() / "kernels" / f"{code}-{identity[:16]}"
    path = folder / "kernel.py"
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f".kernel.{os.getpid()}.tmp"
        temporary.write_text(source, encoding="utf-8")
        try:
            os.link(temporary, path)  # never replaces a file another process wrote
        except FileExistsError:
            pass
        except OSError:  # no hard links on this file system
            if not path.is_file():
                os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
    if path.read_text(encoding="utf-8") != source:
        raise KernelBuildError(f"{path} holds another kernel's source; remove its folder")
    return path


def _load(identity: str, path: Path) -> Any:
    name = f"avk_kernel_{identity[:16]}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _hits(function: Any) -> bool:
    return bool(sum(function.stats.cache_hits.values()) > 0)


def compile_product(
    definition: type[Product], *, bases: tuple[str, ...], device: str = "cpu"
) -> Kernel:
    """Check, schedule, emit and compile `definition` on `bases` for `device`, through the
    disk cache."""
    emitted = emit_product(definition, bases=bases, device=device)
    ir, layout, identity = emitted.ir, emitted.layout, emitted.identity
    started = time.perf_counter()
    path = _module_file(ir.code, identity, emitted.source)
    hit = identity in _LOADED
    if not hit:
        config: Any = numba.config
        if not config.CACHE_DIR:  # Numba was imported before Actuary Valuation Kit set its default
            config.CACHE_DIR = str(numba_cache_dir())
        module = _load(identity, path)
        aggregate, rows = module.run_aggregate, module.run_rows
        if hasattr(aggregate, "compile"):  # absent under NUMBA_DISABLE_JIT=1
            # One array per table of its dimension, then one vector per curve.
            ndims = tuple(len(axes) for _, axes in layout.tables) + (1,) * len(layout.curves)
            signature_aggregate, signature_rows = _signatures(ndims)
            try:
                aggregate.compile(signature_aggregate)
                rows.compile(signature_rows)
            except NumbaError as exc:
                raise KernelBuildError(
                    f"{ir.code}: Numba cannot compile the kernel: {exc}"
                ) from exc
            hit = _hits(aggregate) and _hits(rows)
        _LOADED[identity] = (aggregate, rows)
    aggregate, rows = _LOADED[identity]
    return Kernel(
        identity,
        layout.columns,
        ir.manifest,
        ir,
        layout,
        emitted.source,
        time.perf_counter() - started,
        aggregate,
        rows,
        hit,
        path,
    )
