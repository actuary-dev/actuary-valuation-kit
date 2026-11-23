"""Join measured snapshots by policy, aggregate by declared groups, and call the measure."""

import numpy as np
import polars as pl

from avk.model.measures.ifrs17_rollforward import rollforward
from avk.model.measures.stress import Array
from avk.runs.check import CheckReport
from avk.runs.ifrs17_rollforward_settings import BALANCES, KEYS, OPENING, PRIOR
from avk.runs.ifrs17_settings import month_date, serial
from avk.runtime.errors import ConfigError

# The checked report's product block order is independent of public label spelling.
PRODUCT_ORDER = (
    "TERM",
    "CREDIT_LIFE",
    "ACCIDENTAL_DEATH_RIDER",
    "DISABILITY_RIDER",
    "CRITICAL_ILLNESS_RIDER",
)


def _fraction(numerator: Array, denominator: Array) -> Array:
    share = np.divide(numerator, denominator, out=np.zeros_like(denominator), where=denominator > 0)
    bounded: Array = np.clip(share, 0.0, 1.0)
    return bounded


def build_rollforward(
    report: CheckReport, captured: dict[tuple[str, str], pl.DataFrame]
) -> pl.DataFrame:
    assert report.rollforward_balances is not None
    frames = []
    for code, closing_report in (
        report.products or {report.config.products_to_run[0]: report}
    ).items():
        opening = captured[(code, OPENING)].filter(pl.col("recognised"))
        prior = captured[(code, PRIOR)].filter(pl.col("recognised"))
        # The closing case already carries new business recognised under opening assumptions.
        closing = captured[(code, "Base")].filter(pl.col("recognised"))
        group = ["portfolio", "cohort", "profitability"]
        old_ids = opening.select("Policy_Number")
        prior_existing = prior.join(old_ids, on="Policy_Number", how="semi")
        nb = prior.filter(pl.col("recognised_new_business"))
        # Contracts in the closing data were in force all period; the rest left during it.
        stayed = pl.col("Policy_Number").is_in(closing["Policy_Number"].implode())

        def summarise(frame: pl.DataFrame, **expressions: pl.Expr) -> pl.DataFrame:
            return frame.select(
                "portfolio",
                "cohort",
                "profitability",
                *(expr.alias(name) for name, expr in expressions.items()),
            )

        fcf = pl.col("bel_locked") + pl.col("ra_locked")
        ri_fcf = pl.col("ri_bel_locked") + pl.col("ri_ra_locked")
        pieces = [
            summarise(
                opening,
                opening_policies=pl.lit(1.0),
                opening_claims=pl.col("pv_claims"),
                opening_recoveries=pl.col("pv_recoveries"),
                expected_fcf=pl.col("expected_bel_locked") + pl.col("expected_ra_locked"),
                expected_ri_fcf=pl.col("expected_ri_bel_locked") + pl.col("expected_ri_ra_locked"),
                provided_coverage_units=pl.when(stayed)
                .then(pl.col("survivor_coverage_units"))
                .otherwise(pl.col("leaver_coverage_units")),
                released_outflows=pl.col("released_outflows"),
            ),
            summarise(prior_existing, prior_existing_fcf=fcf, prior_existing_ri_fcf=ri_fcf),
            summarise(
                prior,
                prior_fcf=fcf,
                prior_ri_fcf=ri_fcf,
                prior_claims=pl.col("pv_claims"),
                prior_recoveries=pl.col("pv_recoveries"),
            ),
            summarise(
                closing,
                closing_fcf=fcf,
                closing_ri_fcf=ri_fcf,
                closing_claims=pl.col("pv_claims"),
                closing_recoveries=pl.col("pv_recoveries"),
                future_coverage_units=pl.col("pv_coverage_units"),
                # Outflows and RA still to be released: claims, claim and maintenance expenses.
                future_outflows=pl.col("bel_locked")
                + pl.col("pv_premiums")
                - pl.col("pv_acquisition")
                + pl.col("ra_locked"),
                bel_current=pl.col("bel_current"),
                ra_current=pl.col("ra_current"),
                ri_bel_current=pl.col("ri_bel_current"),
                ri_ra_current=pl.col("ri_ra_current"),
            ),
            summarise(
                nb,
                csm_new_business=pl.col("csm_at_recognition"),
                loss_component_new_business=pl.col("loss_component"),
                ri_csm_new_business=pl.col("ri_csm_at_recognition"),
                loss_recovery_component_new_business=pl.col("loss_recovery_component"),
                csm_nb_interest=pl.col("csm_interest"),
                loss_nb_interest=pl.col("nb_loss_interest"),
                ri_nb_interest=pl.col("ri_csm_interest"),
                recovery_nb_interest=pl.col("nb_recovery_interest"),
                provided_coverage_units=pl.col("nb_coverage_units"),
                released_outflows=pl.col("nb_released_outflows"),
            ),
        ]
        facts = pl.concat(pieces, how="diagonal_relaxed").fill_null(0.0)
        numeric = [c for c in facts.columns if c not in group]
        facts = facts.group_by(group, maintain_order=True).agg(pl.col(numeric).sum())
        facts = facts.with_columns(pl.lit(code).alias("Product"))
        balances = report.rollforward_balances.filter(pl.col("Product") == code)
        facts = facts.join(balances, on=KEYS, how="full", coalesce=True).fill_null(0.0)
        arrays = {c: facts[c].to_numpy() for c in facts.columns if c not in KEYS}
        # IFRS 17 B119F: loss recovery cannot exceed the share of the loss expected to be
        # recovered, measured on the opening data and assumptions.
        allowed = arrays["loss_component"] * _fraction(
            arrays["opening_recoveries"], arrays["opening_claims"]
        )
        excess = arrays["loss_recovery_component"] - allowed
        if (excess > 0.01 + 1e-9 * arrays["loss_component"]).any():
            bad = facts.filter(pl.Series(excess > 0.01 + 1e-9 * arrays["loss_component"]))
            raise ConfigError(
                "IFRS17 roll-forward: opening loss recovery exceeds the share of the opening "
                "loss expected to be recovered (IFRS 17 B119F) for "
                + ", ".join("/".join(map(str, row)) for row in bad.select(KEYS).iter_rows())
            )
        settings = closing_report.measurement
        assert settings is not None
        months = settings.reporting_months
        first = month_date(serial(closing_report.config.valuation_date) - months + 1)
        # Only opening groups carry a balance through the whole period; a group that holds
        # only new business may have no curve before its first issue month.
        held = arrays["opening_policies"] > 0
        growth = np.zeros(facts.height)
        if held.any():
            cohorts = facts.filter(pl.Series(held))["cohort"].to_list()
            growth[held] = np.prod(1 + settings.locked_rates(cohorts, first, months), axis=1) - 1
        for name, extra in zip(
            BALANCES,
            ("csm_nb_interest", "loss_nb_interest", "ri_nb_interest", "recovery_nb_interest"),
            strict=True,
        ):
            arrays[f"{name}_interest"] = arrays[name] * growth + arrays[extra]
        for prefix in ("prior", "closing"):
            arrays[f"{prefix}_fraction"] = _fraction(
                arrays[f"{prefix}_recoveries"], arrays[f"{prefix}_claims"]
            )
        for target, provided, future in (
            ("release_fraction", "provided_coverage_units", "future_coverage_units"),
            ("loss_release_fraction", "released_outflows", "future_outflows"),
        ):
            total = arrays[provided] + arrays[future]
            arrays[target] = np.divide(
                arrays[provided], total, out=np.zeros_like(growth), where=total > 0
            )
        result = rollforward(arrays)
        frames.append(
            facts.select(KEYS).with_columns(
                *(pl.Series(name, value) for name, value in result.items()),
                *(
                    pl.Series(name, arrays[name])
                    for name in (
                        "bel_current",
                        "ra_current",
                        "ri_bel_current",
                        "ri_ra_current",
                        "provided_coverage_units",
                        "future_coverage_units",
                        "release_fraction",
                        "released_outflows",
                        "future_outflows",
                        "loss_release_fraction",
                    )
                ),
            )
        )
    product_rank = pl.col("Product").replace_strict(
        {product: rank for rank, product in enumerate(PRODUCT_ORDER)}, default=len(PRODUCT_ORDER)
    )
    return pl.concat(frames).sort(product_rank, *KEYS)
