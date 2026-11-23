"""Group-level GMM movements; float64 arrays and no definition/configuration objects."""

import numpy as np

from avk.model.measures.stress import Array


def period_service(
    coverage: Array,
    inforce: Array,
    outflows_end: Array,
    outflows_start: Array,
    ra: Array,
    locked: Array,
    months: int,
) -> dict[str, Array]:
    """One snapshot's service in months 1..`months`, valued at period end.

    Amounts accumulate to period end at the locked rates with the PV timing (cover and
    claims at month end, expenses at month start), so they are on the basis of the
    period-end PVs they are divided by (IFRS 17 B119(b); discounting is the BC282 choice).

    Coverage is the cover actually provided (TRG S09): a contract still in force at period
    end provided its full in-force cover; one that left provided its cover in force,
    weighted by the projection's chance of still being in force given that it left in the
    period. Released outflows are the expected claims, claim and maintenance expenses and
    risk-adjustment release (IFRS 17 paragraphs 50-52, IE40).
    """
    count = coverage.shape[0]
    rates = np.broadcast_to(locked, coverage.shape)[:, 1 : months + 1]
    start = np.cumprod((1 + rates)[:, ::-1], axis=1)[:, ::-1]
    end = np.concatenate([start[:, 1:], np.ones((count, 1))], axis=1)
    lives = np.nan_to_num(inforce[:, : months + 1])
    survival = np.divide(lives, lives[:, :1], out=np.zeros_like(lives), where=lives[:, :1] > 0)
    alive, last = survival[:, 1:], survival[:, months:]
    cover = np.nan_to_num(coverage[:, 1 : months + 1])
    per_life = np.divide(cover, alive, out=np.zeros_like(cover), where=alive > 0)
    leaving = 1.0 - last
    # A contract the projection cannot lose still left: assume exits spread evenly.
    even = np.broadcast_to(1.0 - np.arange(1, months + 1) / months, alive.shape)
    weights = np.divide(alive - last, leaving, out=even.copy(), where=leaving > 1e-12)
    released = (
        np.sum(np.nan_to_num(outflows_end[:, 1 : months + 1]) * end, axis=1)
        + np.sum(np.nan_to_num(outflows_start[:, 1 : months + 1]) * start, axis=1)
        + np.nan_to_num(ra[:, 0]) * start[:, 0]
        - np.nan_to_num(ra[:, months])
    )
    return {
        "survivor_coverage_units": np.sum(per_life * end, axis=1),
        "leaver_coverage_units": np.sum(per_life * weights * end, axis=1),
        "released_outflows": released,
    }


def rollforward(values: dict[str, Array]) -> dict[str, Array]:
    """Roll direct margin/loss and signed held cost/loss recovery in fixed order.

    Held CSM includes loss-recovery income. Its future-service movement
    therefore equals held FCF change plus the corresponding loss-recovery change.
    Margins release by coverage units; loss and loss recovery release by the expected
    outflows and risk adjustment released.
    """
    result: dict[str, Array] = {}
    csm = values["csm"]
    loss = values["loss_component"]
    held = values["ri_csm"]
    recovery = values["loss_recovery_component"]

    def save(stage: str, amounts: tuple[Array, Array, Array, Array]) -> None:
        for name, amount in zip(
            ("csm", "loss_component", "ri_csm", "loss_recovery_component"), amounts, strict=True
        ):
            # Adding zero turns IEEE negative zero (-0.0 * factor) into 0.0.
            result[f"{name}_{stage}"] = amount + 0.0

    save("opening", (csm, loss, held, recovery))
    for stage in ("new_business", "interest"):
        dc, dl, dh, dr = (
            values[f"{name}_{stage}"]
            for name in ("csm", "loss_component", "ri_csm", "loss_recovery_component")
        )
        save(stage, (dc, dl, dh, dr))
        csm, loss, held, recovery = csm + dc, loss + dl, held + dh, recovery + dr
    for stage, delta, ri_delta, fraction in (
        (
            "experience",
            values["prior_existing_fcf"] - values["expected_fcf"],
            values["prior_existing_ri_fcf"] - values["expected_ri_fcf"],
            values["prior_fraction"],
        ),
        (
            "assumptions",
            values["closing_fcf"] - values["prior_fcf"],
            values["closing_ri_fcf"] - values["prior_ri_fcf"],
            values["closing_fraction"],
        ),
    ):
        net = csm - loss - delta
        next_csm, next_loss = np.maximum(net, 0.0), np.maximum(-net, 0.0)
        change = (next_loss - loss) * fraction
        if stage == "assumptions":
            change = change + loss * (fraction - values["prior_fraction"])
        next_recovery = np.clip(recovery + change, 0.0, next_loss * fraction)
        if stage == "experience":
            next_recovery = np.where(values["opening_policies"] > 0, next_recovery, recovery)
        dr = next_recovery - recovery
        dh = ri_delta + dr
        save(stage, (next_csm - csm, next_loss - loss, dh, dr))
        csm, loss, held, recovery = next_csm, next_loss, held + dh, next_recovery
    margin, onerous = values["release_fraction"], values["loss_release_fraction"]
    save("release", (-csm * margin, -loss * onerous, -held * margin, -recovery * onerous))
    save(
        "closing",
        (csm * (1 - margin), loss * (1 - onerous), held * (1 - margin), recovery * (1 - onerous)),
    )
    return result
