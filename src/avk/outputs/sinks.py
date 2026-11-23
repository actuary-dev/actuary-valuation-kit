"""Sinks write formatted frames.

Floats are written with the shortest representation that reads back to the same double;
NaN is written as an empty field. A stream writes its header once and appends rows per
batch, so a per-policy-month file never sits in memory whole.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Protocol

import polars as pl

from avk.runtime.errors import OutputError


def _csv_ready(frame: pl.DataFrame) -> pl.DataFrame:
    floats = [name for name, dtype in frame.schema.items() if dtype.is_float()]
    return frame.with_columns(pl.col(floats).fill_nan(None)) if floats else frame


class Stream(Protocol):
    def append(self, frame: pl.DataFrame) -> None: ...


class CsvStream:
    def __init__(self, handle: IO[bytes], path: Path) -> None:
        self.handle = handle
        self.path = path
        self.columns: list[str] | None = None

    def append(self, frame: pl.DataFrame) -> None:
        if self.columns is not None and frame.columns != self.columns:
            raise OutputError(f"{self.path}: a batch changed the columns")
        try:
            _csv_ready(frame).write_csv(
                self.handle, include_header=self.columns is None, null_value=""
            )
        except OSError as exc:
            raise OutputError(f"Cannot write {self.path}: {exc}") from exc
        self.columns = frame.columns


class CsvSink:
    """CSV files in one folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def path(self, name: str) -> Path:
        return self.folder / f"{name}.csv"

    def write_table(self, name: str, frame: pl.DataFrame) -> Path:
        with self.open_stream(name) as stream:
            stream.append(frame)
        return self.path(name)

    @contextmanager
    def open_stream(self, name: str) -> Iterator[CsvStream]:
        path = self.path(name)
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            handle = path.open("wb")
        except OSError as exc:
            raise OutputError(f"Cannot write {path}: {exc}") from exc
        with handle:
            yield CsvStream(handle, path)
