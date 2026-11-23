"""Resolve names once; load only requested tables and fingerprint their contents."""

import csv
import hashlib
import io
import logging
import mmap
import tempfile
import warnings
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from avk.inputs.registry import BUILTIN_FORMATS, InputSpec, Location
from avk.runtime.errors import InputError, reader_failure
from avk.runtime.progress import ACTIVE, fingerprint


class CsvSource:
    @staticmethod
    def read(source: Path | io.BytesIO) -> pl.DataFrame:
        return pl.read_csv(source, infer_schema_length=None, null_values=["NA", "N/A"])


class ParquetSource:
    @staticmethod
    def read(source: Path | io.BytesIO) -> pl.DataFrame:
        return pl.read_parquet(source)


class SqlSource:
    @staticmethod
    def read(location: Location) -> pl.DataFrame:
        raise InputError("SQL input is not yet supported")


def _path(base: Path, name: str) -> Path:
    requested = Path(name)
    path = (base / requested).absolute()
    # Warn only when the filesystem actually resolves the mismatched spelling.
    if path.exists():
        for part in (path, *path.parents):
            if part.parent == part:
                break
            try:
                matches = [
                    p.name
                    for p in part.parent.iterdir()
                    if p.name.casefold() == part.name.casefold()
                ]
            except OSError:
                continue
            if matches and part.name not in matches:
                warnings.warn(
                    f"Input path case mismatch: {part} (on disk: {matches[0]})", stacklevel=2
                )
    return path.resolve()


class _SpoolMapping(mmap.mmap):
    """Keep the spool alive until the last Arrow view releases its mapping."""

    spool: tempfile.TemporaryDirectory[str]

    def __del__(self) -> None:
        # mmap's buffer consumers retain this object. Close before the spool's
        # last reference disappears; Windows cannot unlink an open mapping.
        self.close()


@dataclass
class ResolvedInputs:
    locations: dict[str, Location]
    fingerprints: dict[str, str] = field(default_factory=dict)
    _frames: dict[str, pl.DataFrame] = field(default_factory=dict)
    read_log: list[str] = field(default_factory=list)
    _spools: list[Any] = field(default_factory=list)

    def temporary(self) -> Path:
        spool = tempfile.TemporaryDirectory(prefix="avk-policies-")
        self._spools.append(spool)
        return Path(spool.name) / "policies.arrow"

    def map_prepared(self, path: Path) -> mmap.mmap:
        with path.open("rb") as handle:
            mapping = _SpoolMapping(handle.fileno(), 0, access=mmap.ACCESS_READ)
        mapping.spool = self._spools[-1]
        return mapping

    def policy_batches(self, name: str, size: int) -> Iterator[pl.DataFrame]:
        """Arrow decodes only bounded batches; the source payload is never read_bytes."""
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]

        location = self.location(name)
        assert location.path is not None
        path = Path(location.path)
        try:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            self.fingerprints[name] = digest
            fingerprint(path, digest)
            self.read_log.append(name)
            counts = {"rows": 0, "batches": 0, "batch_rows": 0}
            audit = ACTIVE.get()
            if audit is not None:
                audit.record.setdefault("policy_sources", {})[str(path)] = counts
            with pq.ParquetFile(path) as source:
                for batch in source.iter_batches(batch_size=size, use_threads=False):
                    frame = pl.from_arrow(batch)
                    assert isinstance(frame, pl.DataFrame)
                    frame = frame.rename({c: c.strip() for c in frame.columns})
                    counts["rows"] += frame.height
                    counts["batches"] += 1
                    counts["batch_rows"] = max(counts["batch_rows"], frame.height)
                    yield frame
        except (OSError, pa.ArrowException, pl.exceptions.PolarsError) as exc:
            raise InputError(reader_failure(name, path, exc)) from exc

    def replacing(self, replacements: dict[str, Location]) -> "ResolvedInputs":
        """A case-local registry sharing unchanged, already-read input payloads."""
        unchanged = set(self.locations) - set(replacements)
        return ResolvedInputs(
            {**self.locations, **replacements},
            {name: digest for name, digest in self.fingerprints.items() if name in unchanged},
            {name: frame for name, frame in self._frames.items() if name in unchanged},
        )

    def with_frame(self, name: str, frame: pl.DataFrame) -> None:
        """Install a case-local parameter payload without changing the source frame."""
        self._frames[name] = frame
        self.fingerprints[name] = hashlib.sha256(frame.write_csv().encode()).hexdigest()

    def names(self) -> list[str]:
        return list(self.locations)

    def location(self, name: str) -> Location:
        try:
            return self.locations[name]
        except KeyError as exc:
            raise InputError(f"Input table {name!r} is not registered") from exc

    def format_of(self, name: str) -> str:
        location = self.location(name)
        result = location.format or BUILTIN_FORMATS.get(name)
        if result is None:
            raise InputError(f"{name}: Format must be declared for an unknown table")
        return result

    def read(self, name: str) -> pl.DataFrame:
        if name in self._frames:
            return self._frames[name].clone()
        location = self.location(name)
        if location.source == "sql":
            return SqlSource.read(location)
        if location.source == "generator":
            raise InputError(f"{name}: generator input is not yet supported by table readers")
        assert location.path is not None
        path = Path(location.path)
        if location.source == "parquet":
            import pyarrow.ipc as ipc  # type: ignore[import-untyped]

            spool = self.temporary()
            with spool.open("wb") as handle:
                writer = None
                try:
                    for batch in self.policy_batches(name, 8192):
                        table = batch.to_arrow()
                        if writer is None:
                            writer = ipc.new_file(handle, table.schema)
                        writer.write_table(table)
                finally:
                    if writer is not None:
                        writer.close()
            if writer is None:
                raise InputError(f"{name}: has no policies")
            frame = pl.read_ipc(spool, memory_map=True)
            self._frames[name] = frame
            return frame.clone()
        try:
            # One disk read serves both the fingerprint and the parse.
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            fingerprint(path, digest)
            frame = (CsvSource if location.source == "csv" else ParquetSource).read(
                io.BytesIO(content)
            )
            self.fingerprints[name] = digest
        except (OSError, pl.exceptions.PolarsError) as exc:
            line = None
            if isinstance(exc, pl.exceptions.PolarsError):
                try:
                    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), strict=True)
                    deque(reader, maxlen=0)  # Error path only; no policy preparation here.
                except csv.Error:
                    line = reader.line_num
                except UnicodeError:
                    pass
            raise InputError(reader_failure(name, path, exc, line)) from exc
        frame = frame.rename({column: column.strip() for column in frame.columns})
        self._frames[name] = frame
        self.read_log.append(name)
        logging.getLogger(__name__).info("Read input table %s (%s)", name, path)
        return frame.clone()


class Sources:
    @staticmethod
    def resolve(spec: InputSpec, *, base: Path) -> ResolvedInputs:
        locations: dict[str, Location] = {}
        if spec.tables is not None:
            index = _path(base, spec.tables)
            try:
                fingerprint(index)
                frame = CsvSource.read(index)
                required = {"TableName", "FolderName", "FileName"}
                if not required.issubset(frame.columns):
                    raise InputError(
                        f"{index}: missing table-list columns "
                        f"{sorted(required - set(frame.columns))}"
                    )
                if frame["TableName"].null_count() or frame["TableName"].n_unique() != frame.height:
                    raise InputError(f"{index}: table names must be nonempty and unique")
                for row in frame.iter_rows(named=True):  # table metadata, never policy rows
                    name = str(row["TableName"])
                    source = row.get("Source") or "csv"
                    args = {"Source": source, "Format": row.get("Format")}
                    if source == "sql":
                        args.update(Connection=row.get("Connection"), Table=row["FileName"])
                    else:
                        if not row["FileName"]:
                            raise InputError(f"{name}: FileName is required")
                        args["Path"] = str(
                            _path(index.parent / (row["FolderName"] or ""), row["FileName"])
                        )
                    locations[name] = Location.model_validate(args)
            except (OSError, pl.exceptions.PolarsError, ValueError) as exc:
                raise InputError(reader_failure("Tables", index, exc)) from exc
        for name, replacement in spec.replace.items():
            location = (
                Location.model_validate({"Path": replacement})
                if isinstance(replacement, str)
                else replacement
            )
            updates: dict[str, object] = {}
            if location.path:
                updates["path"] = str(_path(base, location.path))
            if location.format is None and name in locations:
                updates["format"] = locations[name].format
            locations[name] = location.model_copy(update=updates)
        for name, location in locations.items():
            if location.source == "sql" and location.connection not in spec.connections:
                raise InputError(f"{name}: unknown connection {location.connection!r}")
        return ResolvedInputs(locations)
