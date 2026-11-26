"""Frozen, strictly parsed per-run input locations."""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class Location(FrozenSpec):
    source: Literal["csv", "parquet", "sql", "generator"] = Field("csv", alias="Source")
    path: str | None = Field(None, alias="Path")
    format: str | None = Field(None, alias="Format")
    connection: str | None = Field(None, alias="Connection")
    table: str | None = Field(None, alias="Table")
    query: str | None = Field(None, alias="Query")
    generator: str | None = Field(None, alias="Generator")
    settings: dict[str, Any] = Field(default_factory=dict, alias="Settings")

    @model_validator(mode="after")
    def location_required(self) -> Self:
        if self.source in ("csv", "parquet") and not self.path:
            raise ValueError("Path is required for a file input")
        if self.source == "sql" and (not self.connection or bool(self.table) == bool(self.query)):
            raise ValueError("SQL needs Connection and exactly one of Table or Query")
        if self.source == "generator" and not self.generator:
            raise ValueError("Generator is required")
        return self


class Connection(FrozenSpec):
    kind: str = Field(alias="Kind")
    host: str = Field(alias="Host")
    database: str = Field(alias="Database")
    port: int | None = Field(None, alias="Port")


class InputSpec(FrozenSpec):
    tables: str | None = Field(None, alias="Tables")
    replace: dict[str, str | Location] = Field(default_factory=dict, alias="Replace")
    scenarios: Location | None = Field(None, alias="Scenarios")
    connections: dict[str, Connection] = Field(default_factory=dict, alias="Connections")


BUILTIN_FORMATS = {
    "mortality": "avk_mortality_v1",
    "reinsurance_mortality": "avk_mortality_v1",
    "reinsurance_mortality_credit_life": "avk_mortality_v1",
    "mortality_loadings_term": "avk_bands_v1",
    "mortality_loadings_credit_life": "avk_mortality_v1",
    "reinsurance_mortality_loadings_term": "avk_bands_v1",
    "morbidity": "avk_morbidity_v1",
    "reinsurance_morbidity": "avk_morbidity_v1",
    "lapse_rates_term": "avk_lapse_v1",
    "lapse_rates_credit_life": "avk_lapse_v1",
    "commissions_term": "avk_commission_v1",
    "commissions_credit_life": "avk_commission_v1",
    "interest_rates": "avk_curves_v1",
    "ifrs17_interest_rates": "avk_curves_v1",
    "premium_frequency_factors": "avk_frequencies_v1",
    "product_parameters": "avk_parameters_v1",
    **{f"expenses_{f}": "avk_expenses_v1" for f in ("term", "rider", "credit_life")},
    **{f"ifrs17_initial_expenses_{f}": "avk_expenses_v1" for f in ("term", "rider", "credit_life")},
    **{f"ifrs17_renewal_expenses_{f}": "avk_expenses_v1" for f in ("term", "rider", "credit_life")},
    **{name: "avk_ul_keyed_v1" for name in ("ul_funds", "ul_variants", "ul_regulatory_caps")},
    **{
        name: "avk_ul_year_key_v1"
        for name in ("ul_charge_scales", "ul_disc_charge_caps", "ul_riy_caps")
    },
    "mortality_charges_ul": "avk_mortality_v1",
    "lapse_rates_ul": "avk_lapse_v1",
    "partial_withdrawals_ul": "avk_lapse_v1",
    "commissions_ul": "avk_commission_v1",
    "ul_asset_returns": "avk_curves_v1",
}
