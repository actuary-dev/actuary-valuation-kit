"""Batches: how many policies' per-policy-month rows are produced and streamed at a time.

A batch bounds memory only. Aggregates are summed in the executor's fixed logical blocks, so
the batch size never changes a number; it appears in output only as the diagnostics'
`Batch_Index`.
"""

from collections.abc import Mapping

import polars as pl

from avk.model.data import ModelPoints
from avk.runs.config import RunConfig
from avk.runtime.errors import InputError


def batch_size(config: RunConfig) -> int:
    """Policies per batch: the run's `Batch_Size` (strictly positive, validated on load)."""
    return config.batch_size


def group_by_code(points: ModelPoints[pl.DataFrame]) -> Mapping[str, ModelPoints[pl.DataFrame]]:
    """Partition prepared or adapter-tagged rows, retaining each code's source ordering."""
    if "Product_Code" not in points.frame.columns or points.frame["Product_Code"].null_count():
        raise InputError("Model points require nonnull Product_Code")
    return {
        str(key[0]): ModelPoints(frame, points.fields)
        for key, frame in points.frame.partition_by(
            "Product_Code", as_dict=True, maintain_order=True
        ).items()
    }
