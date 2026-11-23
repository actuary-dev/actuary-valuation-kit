"""The three fixed checked cases and strict opening group balances."""

from typing import TYPE_CHECKING

import numpy as np
import polars as pl

from avk.inputs.formats import FormatSpec, read
from avk.products.registry import ProductRegistry
from avk.runs.config import RunConfig
from avk.runs.ifrs17_settings import month_date, serial
from avk.runs.overrides import parse_overrides
from avk.runtime.errors import AvkError, ConfigError

if TYPE_CHECKING:
    from avk.runs.check import CheckReport

KEYS = ["Product", "portfolio", "cohort", "profitability"]
BALANCES = ["csm", "loss_component", "ri_csm", "loss_recovery_component"]
OPENING, PRIOR = "Opening", "Prior assumptions"
# Per-policy new-business service and interest from recognition to closing.
NB_PERIOD = (
    "nb_coverage_units",
    "nb_released_outflows",
    "nb_loss_interest",
    "nb_recovery_interest",
)


def configure_rollforward(cfg: RunConfig) -> tuple[RunConfig, str | None]:
    raw = cfg.ifrs17
    if not isinstance(raw, dict) or "Roll_Forward" not in raw:
        return cfg, None
    settings = raw["Roll_Forward"]
    if cfg.run_type != "IFRS17" or cfg.cases is not None:
        raise ConfigError("IFRS17 roll-forward requires IFRS17 without additional Cases")
    if not isinstance(settings, dict) or set(settings) != {"Opening", "Opening_Balances"}:
        raise ConfigError("IFRS17 roll-forward requires Opening and Opening_Balances")
    logical = settings["Opening_Balances"]
    if not isinstance(logical, str) or not logical:
        raise ConfigError("IFRS17 roll-forward Opening_Balances must name a logical table")
    opening = parse_overrides(settings["Opening"], "IFRS17 roll-forward Opening")
    if not {"Valuation_Date", "Policy_Data"} <= opening.keys() or not opening["Policy_Data"]:
        raise ConfigError("IFRS17 roll-forward Opening requires date and policy-data overrides")
    policy_names = {
        ProductRegistry.default().for_code(code).policy_table for code in cfg.products_to_run
    }
    if set(opening["Policy_Data"]) != policy_names or set(opening.get("Tables", {})) & policy_names:
        raise ConfigError(
            "IFRS17 roll-forward: declare each opening policy source in Policy_Data only"
        )
    prior = {k: v for k, v in opening.items() if k not in {"Valuation_Date", "Policy_Data"}}
    config = cfg.model_copy(
        update={
            "ifrs17": {k: v for k, v in raw.items() if k != "Roll_Forward"},
            "cases": [
                {"Name": OPENING, "Overrides": opening},
                {"Name": PRIOR, "Overrides": prior},
            ],
        }
    )
    return config, logical


def check_rollforward(report: "CheckReport", logical: str) -> pl.DataFrame:
    try:
        table = report.inputs.read(logical)
        if report.inputs.location(logical).format is not None:
            fmt = report.inputs.format_of(logical)
            loaded = read(fmt, table, FormatSpec(logical, {}, (), (), "", 0, "mixed"))
            group_rows = [str(k).split("|") for k in loaded.axes[0].keys]
            table = pl.DataFrame(group_rows, schema=KEYS, orient="row").hstack(
                pl.DataFrame(loaded.values, schema=BALANCES, orient="row")
            )
        if set(table.columns) != set(KEYS + BALANCES):
            raise ConfigError(f"balances require exactly {KEYS + BALANCES}")
        if any(table.schema[k] == pl.Boolean for k in BALANCES):
            raise ConfigError("balances must be numbers, not Boolean values")
        table = table.select(
            *(pl.col(k).cast(pl.String) for k in KEYS),
            *(pl.col(k).cast(pl.Float64) for k in BALANCES),
        )
        if any(table[k].null_count() for k in table.columns):
            raise ConfigError("balances cannot contain missing values")
        if table.select(pl.struct(KEYS).n_unique()).item() != table.height:
            raise ConfigError("duplicate opening group balances")
        values = table.select(BALANCES).to_numpy()
        if (
            not np.isfinite(values).all()
            or (
                table.select("csm", "loss_component", "loss_recovery_component").to_numpy() < 0
            ).any()
        ):
            raise ConfigError("balances must be finite; only held CSM may be negative")
        if ((table["csm"] > 0) & (table["loss_component"] > 0)).any():
            raise ConfigError("opening direct CSM and loss cannot both be positive")
        if (table["loss_recovery_component"] > table["loss_component"]).any():
            raise ConfigError("opening loss recovery cannot exceed the underlying loss component")
        products = report.products or {report.config.products_to_run[0]: report}
        parents = (report.case_reports[OPENING], report.case_reports[PRIOR], report)
        recognition_dates: list[list[int]] = []
        for parent in parents:
            issue_dates: set[int] = set()
            for child in parent.products.values() if parent.products else (parent,):
                assert child.measurement is not None
                issue_dates.update(
                    serial(d)
                    for d in child.measurement.groups.filter(pl.col("recognised_new_business"))[
                        "start"
                    ]
                    .dt.truncate("1mo")
                    .unique()
                    .to_list()
                )
            recognition_dates.append(sorted(issue_dates))
        opening_keys = []
        for code, closing in products.items():
            opening_parent = report.case_reports[OPENING]
            opening = opening_parent.products.get(code, opening_parent)
            prior_parent = report.case_reports[PRIOR]
            prior = prior_parent.products.get(code, prior_parent)
            assert closing.measurement is not None and opening.measurement is not None
            assert prior.measurement is not None
            months = closing.measurement.reporting_months
            if closing.config.valuation_date != month_date(
                serial(closing.config.valuation_date), end=True
            ):
                raise ConfigError("closing date must be a month end for the monthly roll-forward")
            when = month_date(serial(closing.config.valuation_date) - months, end=True)
            if opening.config.valuation_date != when:
                raise ConfigError("opening date must be the reporting-period opening month end")
            if months >= closing.config.projection_term * 12:
                raise ConfigError("reporting period must fit within the projection horizon")
            old = opening.measurement.groups.filter(pl.col("recognised"))
            # Opening balances accrue interest over the whole period on their cohort curves.
            closing.measurement.locked_rates(
                old["cohort"].unique().to_list(), month_date(serial(when) + 1), months
            )
            now = closing.measurement.groups
            existing = now.filter(pl.col("start") <= when)
            joined = now.join(old, on="Policy_Number", how="inner", suffix="_opening")
            if any(
                (joined[k] != joined[f"{k}_opening"]).any()
                for k in ("start", "portfolio", "cohort", "profitability")
            ):
                raise ConfigError(
                    "existing policy IDs, starts and group keys must be carried from opening"
                )
            if not now.select("Policy_Number", "start").equals(
                prior.measurement.groups.select("Policy_Number", "start")
            ):
                raise ConfigError("prior assumptions must retain closing date and policy data")
            # Reject policy data hidden in Tables: otherwise deriving assumptions could
            # accidentally carry the opening book into the prior-assumptions case.
            if not existing["Policy_Number"].is_in(old["Policy_Number"].implode()).all():
                raise ConfigError("closing contains an unrecorded opening policy")
            for snapshot, dates in zip((opening, prior, closing), recognition_dates, strict=True):
                assert snapshot.points is not None and snapshot.measurement is not None
                groups = snapshot.measurement.groups
                points = snapshot.points.frame.filter(groups["recognised"])
                start = "Policy_start_date" if code == "CREDIT_LIFE" else "Policy Start Date"
                end = points.select(
                    pl.col(start).dt.year() * 12
                    + pl.col(start).dt.month()
                    - 1
                    + pl.col("Policy_Term") * 12
                    + 2
                ).to_series()
                starts = points.select(
                    pl.col(start).dt.year() * 12 + pl.col(start).dt.month() - 1
                ).to_series()
                for at in (serial(snapshot.config.valuation_date), *(d - 1 for d in dates)):
                    if (
                        (starts <= at + 1) & (end - at >= snapshot.config.projection_term * 12)
                    ).any():
                        raise ConfigError(
                            "projection horizon must cover every recognised contract, "
                            "including recognition snapshots"
                        )
            opening_keys.append(
                old.select("portfolio", "cohort", "profitability")
                .unique()
                .with_columns(pl.lit(code).alias("Product"))
            )
        expected = pl.concat(opening_keys).select(KEYS)
        if (
            expected.join(table, on=KEYS, how="anti").height
            or table.join(expected, on=KEYS, how="anti").height
        ):
            raise ConfigError("opening balances must cover exactly the opening groups")
        return table
    except (AvkError, pl.exceptions.PolarsError, ValueError) as exc:
        raise ConfigError(f"IFRS17 roll-forward: {exc}") from exc
