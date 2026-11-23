"""`avk compile`: products by registered code or by source file; and `product_kernel`,
the run layer's one way to compile a kernel.

Three depths: `--explain` checks and schedules (every construct, including curve lookups that
no emitter writes yet); `--list` also emits and hashes, reporting each composition's identity
without compiling; plain `compile` builds each kernel through the disk cache (pre-warming it)
and reports its identity and whether it was loaded rather than compiled.
"""

import hashlib
import importlib.util
import sys
import traceback
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from avk.model.compiler import DefinitionError, build_ir
from avk.model.compiler import explain as explain_ir
from avk.model.ir import ProductIR
from avk.model.kernel import Kernel, KernelBuildError, compile_product, emit_product
from avk.model.lang import Product
from avk.model.manifest import Manifest
from avk.products.registry import ProductRegistry
from avk.runtime.errors import ConfigError, FormulaError, KernelError
from avk.runtime.progress import kernel_built

DEVICES = ("cpu", "gpu")
Depth = Literal["explain", "list", "build"]


@dataclass(frozen=True)
class KernelInfo:
    code: str
    device: str
    bases: tuple[str, ...]
    columns: tuple[str, ...]  # `name` or `name@basis`, in evaluation order
    passes: tuple[str, ...]  # each pass's direction, in order
    manifest: Mapping[str, Manifest]  # reached requirements per basis
    identity: str | None = None  # the kernel identity (listed or built)
    explanation: str | None = None
    composition: tuple[str, ...] = ()  # the product class, then its bases in order
    cache_hit: bool | None = None  # built: loaded from the cache rather than compiled
    compile_seconds: float | None = None  # built: compiling, or loading


def product_ir(definition: type[Product]) -> ProductIR:
    """The definition's IR on its own bases; compiler rejections become `FormulaError`."""
    try:
        return build_ir(definition, bases=tuple(getattr(definition, "BASES", ())))
    except DefinitionError as exc:
        raise FormulaError(str(exc)) from exc


def product_kernel(definition: type[Product], *, device: str = "cpu") -> Kernel:
    """The definition's kernel on all its bases, compiled once for this run."""
    if device not in DEVICES:
        raise ConfigError(f"Unknown device {device!r}: choose from {DEVICES}")
    if device == "gpu":
        raise ConfigError("GPU execution is not available in this release")
    try:
        kernel = compile_product(definition, bases=tuple(getattr(definition, "BASES", ())))
        kernel_built(definition.CODE, kernel.identity)
        return kernel
    except DefinitionError as exc:
        raise FormulaError(str(exc)) from exc
    except KernelBuildError as exc:
        raise KernelError(str(exc)) from exc


@contextmanager
def product_source(path: Path) -> Iterator[type[Product]]:
    """The one product class a source file defines (how product variants are submitted).

    The module is registered only while the caller compiles it (class sources are found
    through their module) and removed afterwards, so nothing outlives the call.
    """
    path = path.resolve()
    if not path.is_file():
        raise ConfigError(f"Product source not found: {path}")
    name = "avk_source_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"Not a Python source file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            line = getattr(exc, "lineno", None) if isinstance(exc, SyntaxError) else None
            for frame in traceback.extract_tb(exc.__traceback__):
                if Path(frame.filename) == path:
                    line = frame.lineno
            raise FormulaError(
                f"{path}:{line or 1}: cannot load product source: {type(exc).__name__}: {exc}"
            ) from exc
        products = [
            item
            for item in vars(module).values()
            if isinstance(item, type)
            and issubclass(item, Product)
            and item.__module__ == name
            and "CODE" in vars(item)
        ]
        if len(products) != 1:
            found = ", ".join(item.__name__ for item in products) or "none"
            raise FormulaError(
                f"{path}:1: a product source defines exactly one product class "
                f"(a Product subclass declaring CODE); found {found}"
            )
        yield products[0]
    finally:
        sys.modules.pop(name, None)


def _info(definition: type[Product], device: str, depth: Depth) -> KernelInfo:
    ir = product_ir(definition)
    labels = {q.key: q.label for q in ir.quantities if q.kind != "binding"}
    info = KernelInfo(
        ir.code,
        device,
        ir.bases,
        tuple(labels[key] for stage in ir.passes for key in stage.members),
        tuple(stage.direction for stage in ir.passes),
        ir.manifest,
        explanation=explain_ir(ir) if depth == "explain" else None,
        composition=(definition.__name__, *(base.__name__ for base in definition.__bases__)),
    )
    if depth == "list":
        try:
            emitted = emit_product(definition, bases=ir.bases, device=device)
        except DefinitionError as exc:
            raise FormulaError(str(exc)) from exc
        return replace(info, identity=emitted.identity)
    if depth == "build":
        kernel = product_kernel(definition, device=device)
        return replace(
            info,
            identity=kernel.identity,
            cache_hit=kernel.cache_hit,
            compile_seconds=kernel.compile_seconds,
        )
    return info


def compile_products(
    codes: Sequence[str] = (),
    *,
    device: str = "cpu",
    explain: bool = False,
    listing: bool = False,
) -> list[KernelInfo]:
    """Every named code or product source file (every registered code when none): explained,
    listed with identities, or built through the disk cache (the default)."""
    if device not in DEVICES:
        raise ConfigError(f"Unknown device {device!r}: choose from {DEVICES}")
    if device == "gpu":
        raise ConfigError("GPU execution is not available in this release")
    depth: Depth = "explain" if explain else "list" if listing else "build"
    registry = ProductRegistry.default()
    infos = []
    for code in codes or registry.codes():
        if code in registry.codes():
            infos.append(_info(registry.for_code(code).definition(), device, depth))
        elif code.endswith(".py") or Path(code).is_file():
            with product_source(Path(code)) as definition:
                infos.append(_info(definition, device, depth))
        else:
            raise ConfigError(f"Unknown product code: {code}")
    return infos
