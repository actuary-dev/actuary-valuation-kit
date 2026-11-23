"""Run-scoped audit state and atomic progress files, without global logging changes."""

import hashlib
import json
import logging
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

ACTIVE: ContextVar["Audit | None"] = ContextVar("avk_audit", default=None)


def fingerprint(path: Path, digest: str | None = None) -> None:
    audit = ACTIVE.get()
    if audit is None:
        return
    path = path.resolve()
    if digest is None:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    audit.record["inputs"][str(path)] = {"path": str(path), "sha256": digest}


def generated_file(role: str, path: Path) -> None:
    """Generated artifacts are provenance, separate from supplied input identities."""
    audit = ACTIVE.get()
    if audit is not None:
        path = path.resolve()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        audit.record.setdefault("generated_files", {})[role] = {
            "name": str(path),
            "sha256": digest,
        }


def kernel_built(code: str, identity: str) -> None:
    audit = ACTIVE.get()
    if audit is not None:
        audit.record["kernel_identities"][code] = identity
        audit.status("projecting")


def checked(report: Any) -> None:
    audit = ACTIVE.get()
    if audit is not None:
        audit.record["cases"] = ["Base", *[c.name for c in report.cases]]
        audit.record["product_summaries"] = list(report.product_summaries)
        audit.record["stresses"] = [s.risk for s in report.stresses]
        audit.status("projecting")


class Audit(logging.Handler):
    """One handler per run, selected by context (including nested/concurrent runs)."""

    def __init__(self, output: Path, settings: dict[str, Any], progress: Any) -> None:
        super().__init__(logging.NOTSET)
        output.mkdir(parents=True, exist_ok=True)
        self.output = output
        self.progress = progress
        self.begun = time.perf_counter()
        self.record: dict[str, Any] = {
            "status": "running",
            "settings": settings,
            "inputs": {},
            "engine_version": version("actuary-valuation-kit"),
            "kernel_identities": {},
            "cases": [],
            "timings": {},
            "started_at": datetime.now(UTC).isoformat(),
        }
        (output / "main.log").write_text("Run started\n", encoding="utf-8")
        (output / "error.log").write_text("", encoding="utf-8")
        self.status("validating", notify=False)

    def write(self, name: str, data: dict[str, Any]) -> None:
        path = self.output / name
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def status(self, stage: str, *, notify: bool = True) -> None:
        state = {"status": self.record["status"], "stage": stage}
        self.write("run_status.json", state)
        self.write("run_record.json", self.record)
        if notify and callable(self.progress):
            self.progress(dict(state))

    def emit(self, record: logging.LogRecord) -> None:
        if ACTIVE.get() is self:
            with (self.output / "main.log").open("a", encoding="utf-8") as stream:
                stream.write(self.format(record) + "\n")

    def finish(self, result: Any = None, error: BaseException | None = None) -> None:
        self.record["status"] = "failed" if error is not None else "completed"
        if result is not None:
            self.record.update(result.manifest)
            self.record["timings"] = dict(result.timings)
        if error is not None:
            message = f"{type(error).__name__}: {error}"
            self.record["error"] = message
            (self.output / "error.log").write_text(message + "\n", encoding="utf-8")
        self.record["timings"]["wall"] = time.perf_counter() - self.begun
        self.record["finished_at"] = datetime.now(UTC).isoformat()
        with (self.output / "main.log").open("a", encoding="utf-8") as stream:
            stream.write(f"Run {self.record['status']}\n")
        self.status(self.record["status"], notify=error is None)
