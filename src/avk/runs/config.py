"""Strict run configuration and product parameter loading."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import Field, PrivateAttr, ValidationError, field_validator, model_validator

from avk.assumptions.models import ProductParameters
from avk.inputs.registry import FrozenSpec, InputSpec
from avk.runs.scenario_statistics import Tail
from avk.runtime.errors import ConfigError, reader_failure

ProductConfig = ProductParameters

RUN_TYPES = (
    "Valuation",
    "Sensitivities",
    "StressCapital",
    "IFRS17",
)


class ScenarioSummary(FrozenSpec):
    percentiles: tuple[Annotated[float, Field(strict=True, ge=0, le=1)], ...] = Field(
        alias="Percentiles"
    )
    cte_levels: tuple[Annotated[float, Field(strict=True, ge=0, lt=1)], ...] = Field(
        alias="CTE_Levels"
    )
    tail: Tail = Field(alias="Tail")

    @model_validator(mode="after")
    def unique_levels(self) -> Self:
        for name, levels in (("Percentiles", self.percentiles), ("CTE_Levels", self.cte_levels)):
            if len(set(levels)) != len(levels):
                raise ValueError(f"{name} must not contain duplicate levels")
        return self


class DynamicLapseBasis(FrozenSpec):
    enabled: bool = Field(alias="Enabled", strict=True)
    slope: float = Field(alias="Slope", strict=True, ge=0, allow_inf_nan=False)
    floor: float = Field(alias="Floor", strict=True, ge=0, allow_inf_nan=False)
    cap: float = Field(alias="Cap", strict=True, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered_bounds(self) -> Self:
        if self.floor > self.cap:
            raise ValueError("Floor must be at most Cap")
        return self


class DynamicLapse(FrozenSpec):
    reserving: DynamicLapseBasis
    be: DynamicLapseBasis
    mc: DynamicLapseBasis


class RunConfig(FrozenSpec):
    valuation_date: date = Field(alias="Valuation_Date")
    fiscal_start_month: int = Field(ge=1, le=12, strict=True)
    projection_term: int = Field(alias="Projection_Term", gt=0, strict=True)
    run_type: str = Field(alias="Run_Type")
    products_to_run: tuple[str, ...] = Field(alias="Products_to_run", min_length=1)
    output_path: Path = Field(alias="Output_path")
    output_seriatim_cf_flag: Literal[0, 1] = Field(alias="Output_seriatim_cf_flag")
    batch_size: int = Field(alias="Batch_Size", gt=0, strict=True)
    root_folder: Path | None = None
    stream_parquet_path: Path | None = Field(None, alias="Stream_Parquet_Path")
    inputs: InputSpec | None = Field(None, alias="Inputs")
    cases: list[dict[str, Any]] | dict[str, str] | None = Field(None, alias="Cases")
    stress_set: str | dict[str, Any] | None = Field(None, alias="Stress_Set")
    ifrs17: dict[str, Any] | None = Field(None, alias="IFRS17")
    scenario_summary: ScenarioSummary | None = Field(None, alias="Scenario_Summary")
    dynamic_lapse: DynamicLapse | None = Field(None, alias="Dynamic_Lapse")
    device: Literal["cpu", "gpu"] = Field("cpu", alias="Device")
    _path: Path | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_run_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key, guidance in (
                ("Sensitivities_Flag", "use Cases for sensitivity runs"),
                ("sensitivities_flag", "use Cases for sensitivity runs"),
                ("data_source", "declare sources under Inputs"),
            ):
                if key in data:
                    raise ValueError(f"Unknown run-file key {key}. Delete it and {guidance}.")
        return data

    @field_validator("valuation_date", mode="before")
    @classmethod
    def parse_date(cls, value: object) -> object:
        if isinstance(value, str):
            for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, pattern).date()
                except ValueError:
                    pass
        return value

    @field_validator("run_type")
    @classmethod
    def canonical_run(cls, value: str) -> str:
        if value not in RUN_TYPES:
            raise ValueError(f"Run_Type must be one of {', '.join(RUN_TYPES)}")
        return value

    @model_validator(mode="after")
    def valid_products(self) -> Self:
        if len(set(self.products_to_run)) != len(self.products_to_run):
            raise ValueError("Products_to_run must not contain duplicates")
        if self.scenario_summary is not None and self.run_type != "Valuation":
            raise ValueError("Scenario_Summary requires Run_Type Valuation")
        if self.dynamic_lapse is not None and (
            self.run_type != "Valuation" or "UNIT_LINKED" not in self.products_to_run
        ):
            raise ValueError("Dynamic_Lapse requires UNIT_LINKED in a Valuation run")
        return self


def load_run_config(path: str | Path) -> RunConfig:
    path = Path(path).resolve()
    try:
        content = path.read_text(encoding="utf-8-sig")
        data = json.loads(content) if path.suffix.lower() == ".json" else yaml.safe_load(content)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ConfigError(reader_failure("invalid run configuration", path, exc)) from exc
    try:
        config = RunConfig.model_validate(data)
        config._path = path
    except ValidationError as exc:
        raise ConfigError(f"{path}: invalid run configuration: {exc}") from exc
    return config
