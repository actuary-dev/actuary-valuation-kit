"""Unit-linked validation: policy rows, fund holdings, product tables and regulatory caps.

`UnitLinkedPolicyValidator` checks the raw policy and holdings rows (no tables needed).
`check_tables` and `check_policies_against_tables` need the run's loaded tables and are
called by the model-point adapter; both return messages that the caller raises together.
"""

from collections.abc import Callable, Mapping
from datetime import date

import numpy as np
import polars as pl

from avk.inputs.policies import dates, numeric
from avk.inputs.validation import Issue, MaturityRule, PolicyValidator
from avk.model.data import Table
from avk.products.unit_linked import features
from avk.products.unit_linked.bindings import (
    ASSET_CLASSES,
    CAPS_TABLE,
    CODE,
    DISC_CAPS_TABLE,
    FUNDS_TABLE,
    GENDER_CODES,
    HOLDINGS_TABLE,
    MAX_FUND_SLOTS,
    POLICY_TABLE,
    PREMIUM_FREQUENCIES,
    RIY_CAPS_TABLE,
    SCALES_TABLE,
    SMOKER_CODES,
    STATUS_ACTIVE,
    STATUS_DPF,
    STATUS_RPU,
    VARIANTS_TABLE,
)

ALLOCATION_TOLERANCE = 1e-9
WEIGHT_TOLERANCE = 1e-12

POLICY_DATES = ("Policy Start Date", "Valuation Date", "Date of Birth", "Status Date")
POLICY_LAST_PREMIUM = "Date Of Last Premium Paid"
POLICY_NUMBERS = (
    "Policy Term (Years)",
    "Premium Payment Term (Years)",
    "Premium Frequency",
    "Annualised Premium",
    "Sum Assured",
    "Distribution Channel",
    "Age at Policy Start",
    "Underwriting Class",
    "EMR",
    "Flat Extra",
    "Flat Extra Term (Years)",
    "Policy Status",
    "Paid Up Sum Assured",
    "Premiums Paid To Date",
    "Instalments Paid",
    "Premium Allocation Charges To Date",
    "Policy Administration Charges To Date",
    "Mortality Charges To Date",
    "Guarantee Charges To Date",
    "Loyalty Additions To Date",
    "Partial Withdrawals To Date",
    "Withdrawals Current Policy Year",
    "Withdrawals Previous Policy Year",
    "Fund Value Sum Current Policy Year",
    "Discontinuance Charge Paid",
    "Issue Cohort",
    "Profitability Group",
    "Transition Approach",
)
POLICY_TEXT = (
    "Policy Number",
    "Product Code",
    "Product Variant",
    "Currency",
    "Gender",
    "Smoking Status",
    "Portfolio",
    "Measurement Model",
    "Legal Entity",
)
POLICY_COLUMNS = (
    "Policy Number",
    "Product Code",
    "Product Variant",
    "Valuation Date",
    "Policy Start Date",
    "Policy Term (Years)",
    "Premium Payment Term (Years)",
    "Premium Frequency",
    "Annualised Premium",
    "Sum Assured",
    "Distribution Channel",
    "Currency",
    "Date of Birth",
    "Age at Policy Start",
    "Gender",
    "Smoking Status",
    "Underwriting Class",
    "EMR",
    "Flat Extra",
    "Flat Extra Term (Years)",
    "Policy Status",
    "Status Date",
    "Paid Up Sum Assured",
    "Date Of Last Premium Paid",
    *POLICY_NUMBERS[13:25],
    "Portfolio",
    "Issue Cohort",
    "Profitability Group",
    "Transition Approach",
    "Measurement Model",
    "Legal Entity",
)
# Integers among the numeric policy columns, and the code columns with their values.
POLICY_INTEGERS = (
    "Policy Term (Years)",
    "Premium Payment Term (Years)",
    "Distribution Channel",
    "Age at Policy Start",
    "Underwriting Class",
    "Flat Extra Term (Years)",
    "Instalments Paid",
    "Issue Cohort",
)
POLICY_CODES = {
    "Premium Frequency": PREMIUM_FREQUENCIES,
    "Policy Status": (STATUS_ACTIVE, STATUS_DPF, STATUS_RPU),
    "Profitability Group": (0, 1, 2),
    "Transition Approach": (0, 1, 2),
}
MEASUREMENT_MODELS = ("VFA", "GMM")

HOLDING_NUMBERS = (
    "Units",
    "Premium Allocation",
    "Premiums Allocated To Fund",
    "Units Allocated To Date",
    "Units Cancelled To Date",
    "Switches In To Date",
    "Switches Out To Date",
    "Guaranteed Unit Price",
)
HOLDING_COLUMNS = (
    "Policy Number",
    "Product Code",
    "Fund Code",
    "Valuation Date",
    "Units",
    "Premium Allocation",
    "Fund Entry Date",
    *HOLDING_NUMBERS[2:],
)


def _missing(frame: pl.DataFrame, columns: tuple[str, ...], table: str) -> list[str]:
    missing = [c for c in columns if c not in frame.columns]
    return [f"{table}: missing required column(s) {missing}"] if missing else []


def _nulls(frame: pl.DataFrame, columns: tuple[str, ...], table: str) -> list[str]:
    nulls = [c for c in columns if frame[c].null_count()]
    return [f"{table}: missing value(s) in {nulls}"] if nulls else []


def _bad_numbers(values: pl.DataFrame, columns: tuple[str, ...], table: str) -> list[str]:
    bad = [c for c in columns if values[c].null_count() or not values[c].is_finite().all()]
    return [f"{table}: non-numeric or non-finite value(s) in {bad}"] if bad else []


def months_elapsed(start: pl.Expr, valuation: date) -> pl.Expr:
    """Policy month at the valuation date, as Term's `Duration_in_Months`."""
    return ((valuation.year - start.dt.year()) * 12 + valuation.month - start.dt.month() + 1).cast(
        pl.Int64
    )


class UnitLinkedPolicyValidator(PolicyValidator):
    maturity_rule = MaturityRule("Policy Start Date", "Policy Term (Years)")

    def __init__(self, code: str = CODE) -> None:
        self.code = code

    def validate(self, frame: pl.DataFrame) -> list[Issue]:
        """Rules on the policy rows alone; dates against the run in `validate_at`."""
        messages = self._policy_messages(frame)
        return [Issue("error", m) for m in messages]

    def validate_at(self, frame: pl.DataFrame, valuation_date: date) -> list[Issue]:
        issues = self.validate(frame)
        if any(issue.severity == "error" for issue in issues):
            return issues
        valuation = dates("Valuation Date", frame.schema["Valuation Date"])
        start = dates("Policy Start Date", frame.schema["Policy Start Date"])
        status = dates("Status Date", frame.schema["Status Date"])
        checks = frame.select(
            (valuation != pl.lit(valuation_date)).any().alias("valuation"),
            (status > pl.lit(valuation_date)).any().alias("status"),
            (start > pl.lit(valuation_date)).any().alias("start"),
        ).row(0, named=True)
        if checks["valuation"]:
            issues.append(
                Issue(
                    "error",
                    f"{POLICY_TABLE}: Valuation Date must equal the run's valuation date "
                    f"{valuation_date.isoformat()}",
                )
            )
        if checks["start"] or checks["status"]:
            issues.append(
                Issue(
                    "error",
                    f"{POLICY_TABLE}: dates must satisfy Policy Start Date <= Status Date "
                    "<= valuation date",
                )
            )
        if any(issue.severity == "error" for issue in issues):
            return issues
        return super().validate_at(frame, valuation_date)

    def _policy_messages(self, frame: pl.DataFrame) -> list[str]:
        table = POLICY_TABLE
        if frame.is_empty():
            return [f"{table}: has no policies"]
        messages = _missing(frame, POLICY_COLUMNS, table)
        if messages:
            return messages
        messages = _nulls(frame, POLICY_COLUMNS, table)
        if messages:
            return messages
        values = frame.select(numeric(c) for c in POLICY_NUMBERS)
        messages = _bad_numbers(values, POLICY_NUMBERS, table)
        parsed = frame.select(
            dates(c, frame.schema[c]) for c in (*POLICY_DATES, POLICY_LAST_PREMIUM)
        )
        unparsed = [c for c in parsed.columns if parsed[c].null_count()]
        if unparsed:
            messages.append(f"{table}: unparseable date(s) in {unparsed}")
        if messages:
            return messages
        if frame["Policy Number"].is_duplicated().any():
            messages.append(f"{table}: duplicate Policy Number")
        if (frame["Product Code"].cast(pl.String) != self.code).any():
            messages.append(f"{table}: Product Code must be {self.code}")
        if frame["Currency"].cast(pl.String).n_unique() != 1:
            messages.append(f"{table}: a run holds a single Currency")
        for column, labels in (("Gender", GENDER_CODES), ("Smoking Status", SMOKER_CODES)):
            if (~frame[column].cast(pl.String).is_in(list(labels))).any():
                messages.append(f"{table}: {column} must be one of {list(labels)}")
        if (~frame["Measurement Model"].cast(pl.String).is_in(MEASUREMENT_MODELS)).any():
            messages.append(f"{table}: Measurement Model must be one of {list(MEASUREMENT_MODELS)}")
        for column in POLICY_INTEGERS:
            series = values[column]
            if (series != series.floor()).any() or (series < 0).any():
                messages.append(f"{table}: {column} must be a nonnegative integer")
        for column, allowed in POLICY_CODES.items():
            if (~values[column].is_in([float(a) for a in allowed])).any():
                messages.append(f"{table}: {column} must be one of {list(allowed)}")
        amounts = [c for c in POLICY_NUMBERS if c not in POLICY_INTEGERS and c not in POLICY_CODES]
        negative = [c for c in amounts if (values[c] < 0).any()]
        if negative:
            messages.append(f"{table}: amounts must be nonnegative: {negative}")
        if messages:
            return messages
        term = values["Policy Term (Years)"]
        ppt = values["Premium Payment Term (Years)"]
        frequency = values["Premium Frequency"]
        if (term <= 0).any():
            messages.append(f"{table}: Policy Term (Years) must be positive")
        if ((frequency == 0) != (ppt == 0)).any():
            messages.append(
                f"{table}: Premium Frequency 0 (single premium) if and only if "
                "Premium Payment Term (Years) is 0"
            )
        if (ppt > term).any():
            messages.append(f"{table}: Premium Payment Term (Years) cannot exceed the term")
        if (values["EMR"] <= 0).any():
            messages.append(f"{table}: EMR must be positive")
        status = values["Policy Status"]
        paid_up = values["Paid Up Sum Assured"]
        if ((paid_up > 0) != (status == STATUS_RPU)).any():
            messages.append(f"{table}: Paid Up Sum Assured > 0 if and only if Policy Status is 2")
        start, birth, since = (
            parsed[c] for c in ("Policy Start Date", "Date of Birth", "Status Date")
        )
        if (since < start).any():
            messages.append(
                f"{table}: dates must satisfy Policy Start Date <= Status Date <= valuation date"
            )
        completed = (
            start.dt.year()
            - birth.dt.year()
            - (
                (start.dt.month() < birth.dt.month())
                | ((start.dt.month() == birth.dt.month()) & (start.dt.day() < birth.dt.day()))
            ).cast(pl.Int32)
        )
        if (completed.cast(pl.Float64) != values["Age at Policy Start"]).any():
            messages.append(
                f"{table}: Age at Policy Start must equal completed years from Date of Birth "
                "to Policy Start Date"
            )
        return messages

    def validate_companions(
        self,
        policies: pl.DataFrame,
        companions: Mapping[str, pl.DataFrame],
        valuation_date: date,
    ) -> list[Issue]:
        """Holding rows of `policies`; rules that need the fund universe run in the adapter."""
        return [
            Issue("error", m)
            for m in holding_messages(policies, companions[HOLDINGS_TABLE], valuation_date)
        ]

    def companion_orphans(
        self,
        known: Callable[[pl.Series], pl.Series],
        companions: Mapping[str, pl.DataFrame],
    ) -> list[Issue]:
        holdings = companions[HOLDINGS_TABLE]
        if "Policy Number" not in holdings.columns:
            return []
        orphans = holdings.filter(~known(holdings["Policy Number"]))
        if orphans.is_empty():
            return []
        count = orphans["Policy Number"].n_unique()
        return [
            Issue(
                "error",
                f"{HOLDINGS_TABLE}: {orphans.height} holding row(s) for {count} Policy Number(s) "
                f"absent from {POLICY_TABLE}",
            )
        ]


def holding_messages(
    policies: pl.DataFrame, holdings: pl.DataFrame, valuation_date: date
) -> list[str]:
    table = HOLDINGS_TABLE
    messages = _missing(holdings, HOLDING_COLUMNS, table)
    if messages:
        return messages
    numbers = policies["Policy Number"]
    rows = holdings.filter(pl.col("Policy Number").is_in(numbers.implode()))
    messages = _nulls(rows, HOLDING_COLUMNS, table)
    if messages:
        return messages
    values = rows.select(
        pl.col("Policy Number", "Fund Code", "Product Code"),
        *(numeric(c) for c in HOLDING_NUMBERS),
        dates("Valuation Date", rows.schema["Valuation Date"]),
        dates("Fund Entry Date", rows.schema["Fund Entry Date"]),
    )
    messages = _bad_numbers(values, HOLDING_NUMBERS, table)
    unparsed = [c for c in ("Valuation Date", "Fund Entry Date") if values[c].null_count()]
    if unparsed:
        messages.append(f"{table}: unparseable date(s) in {unparsed}")
    if messages:
        return messages
    if values.select("Policy Number", "Fund Code").is_duplicated().any():
        messages.append(f"{table}: Policy Number + Fund Code must be unique")
    negative = [c for c in HOLDING_NUMBERS if (values[c] < 0).any()]
    if negative:
        messages.append(f"{table}: values must be nonnegative: {negative}")
    if (values["Premium Allocation"] > 1).any():
        messages.append(f"{table}: Premium Allocation must lie in [0, 1]")
    if (values["Fund Entry Date"] > valuation_date).any():
        messages.append(f"{table}: Fund Entry Date cannot follow the valuation date")
    keys = policies.select(
        pl.col("Policy Number"),
        pl.col("Product Code").cast(pl.String).alias("policy_code"),
        dates("Valuation Date", policies.schema["Valuation Date"]).alias("policy_date"),
        numeric("Policy Status").alias("status"),
        numeric("Premium Payment Term (Years)").alias("ppt"),
        months_elapsed(
            dates("Policy Start Date", policies.schema["Policy Start Date"]), valuation_date
        ).alias("month"),
        numeric("Premiums Paid To Date").alias("paid"),
    )
    joined = values.join(keys, on="Policy Number", how="inner")
    if (
        (joined["Product Code"].cast(pl.String) != joined["policy_code"])
        | (joined["Valuation Date"] != joined["policy_date"])
    ).any():
        messages.append(
            f"{table}: Product Code and Valuation Date must equal the policy's in {POLICY_TABLE}"
        )
    totals = joined.group_by("Policy Number").agg(
        pl.col("Premium Allocation").sum().alias("allocation"),
        pl.col("Premiums Allocated To Fund").sum().alias("allocated"),
        pl.len().alias("holdings"),
    )
    summary = keys.join(totals, on="Policy Number", how="left")
    without = summary.filter(pl.col("holdings").is_null())
    if without.height:
        messages.append(f"{table}: {without.height} policy(ies) hold no fund")
    held = summary.filter(pl.col("holdings").is_not_null())
    if (held["allocated"] > held["paid"] * (1 + 1e-12) + 1e-9).any():
        messages.append(
            f"{POLICY_TABLE}: Premiums Paid To Date must be at least the sum of "
            f"Premiums Allocated To Fund in {table}"
        )
    paying = held.filter(
        (pl.col("status") == STATUS_ACTIVE)
        & (pl.col("ppt") > 0)
        & (pl.col("month") <= pl.col("ppt") * 12)
    )
    if ((paying["allocation"] - 1).abs() > ALLOCATION_TOLERANCE).any():
        messages.append(f"{table}: allocations of a premium-paying policy must sum to 1")
    return messages


def _keyed(table: Table) -> pl.DataFrame:
    return pl.DataFrame(
        {"key": list(table.axes[0].keys)}
        | {str(f): table.values[:, i] for i, f in enumerate(table.axes[1].keys)}
    )


def keyed_frames(tables: Mapping[str, Table]) -> dict[str, pl.DataFrame]:
    """The three keyed tables as frames: a key column then one column per field."""
    return {name: _keyed(tables[name]) for name in (FUNDS_TABLE, VARIANTS_TABLE, CAPS_TABLE)}


def year_table(tables: Mapping[str, Table], logical: str, field: str) -> Table:
    return tables[f"{logical}/{field}"]


def _year_columns(table: Table, key: int) -> np.ndarray:
    return table.values[:, table.axes[1].keys.index(key)]


def check_tables(tables: Mapping[str, Table]) -> list[str]:
    """Rules of the product and regulation tables, before any policy uses them."""
    frames = keyed_frames(tables)
    funds, variants, caps = frames[FUNDS_TABLE], frames[VARIANTS_TABLE], frames[CAPS_TABLE]
    messages = [
        *features.check_rules(funds, features.FUND_FIELDS, FUNDS_TABLE),
        *features.check_rules(variants, features.VARIANT_FIELDS, VARIANTS_TABLE),
        *features.check_rules(caps, features.CAP_FIELDS, CAPS_TABLE),
    ]
    for logical, rules in (
        (SCALES_TABLE, features.SCALE_FIELDS),
        (DISC_CAPS_TABLE, features.DISC_CAP_FIELDS),
    ):
        frame = pl.DataFrame(
            {r.name: year_table(tables, logical, r.name).values.ravel() for r in rules}
        )
        messages.extend(features.check_rules(frame, rules, logical))
    riy = pl.DataFrame({"riy_max": tables[RIY_CAPS_TABLE].values.ravel()})
    messages.extend(features.check_rules(riy, features.RIY_FIELDS, RIY_CAPS_TABLE))
    if messages:
        return messages
    weights = funds.select(f"w_{a}" for a in ASSET_CLASSES).to_numpy().sum(axis=1)
    if (np.abs(weights - 1) > WEIGHT_TOLERANCE).any():
        messages.append(f"{FUNDS_TABLE}: asset weights of a fund must sum to 1")
    dpf = funds.filter(pl.col("is_dpf") == 1)
    if dpf.height != 1 or (dpf["selectable"] != 0).any():
        messages.append(f"{FUNDS_TABLE}: exactly one fund has is_dpf 1 and it has selectable 0")
    for frame, name, field in (
        (variants, VARIANTS_TABLE, "variant_id"),
        (caps, CAPS_TABLE, "regime_id"),
    ):
        if frame[field].is_duplicated().any():
            messages.append(f"{name}: {field} must be unique")
    regimes = set(caps["regime_id"].to_list())
    if not set(variants["regime_id"].to_list()) <= regimes:
        messages.append(f"{VARIANTS_TABLE}: regime_id must exist in {CAPS_TABLE}")
    variant_ids = set(variants["variant_id"].to_list())
    for field in (r.name for r in features.SCALE_FIELDS):
        keys = set(year_table(tables, SCALES_TABLE, field).axes[1].keys)
        if keys != variant_ids:
            messages.append(
                f"{SCALES_TABLE}: keys of {field} must be exactly the variant_ids of "
                f"{VARIANTS_TABLE}"
            )
            break
    year_tables = [
        (DISC_CAPS_TABLE, year_table(tables, DISC_CAPS_TABLE, r.name))
        for r in features.DISC_CAP_FIELDS
    ] + [(RIY_CAPS_TABLE, tables[RIY_CAPS_TABLE])]
    for name, table in year_tables:
        if set(table.axes[1].keys) != regimes:
            messages.append(f"{name}: keys must be exactly the regime_ids of {CAPS_TABLE}")
            break
    if messages:
        return messages
    return messages + _cap_messages(tables, variants, caps)


def _cap_messages(
    tables: Mapping[str, Table], variants: pl.DataFrame, caps: pl.DataFrame
) -> list[str]:
    messages = []
    capped = caps.filter(pl.col("caps_apply") == 1)
    for cap in capped.iter_rows(named=True):  # over regimes and variants, never policies
        regime = int(cap["regime_id"])
        for row in variants.filter(pl.col("regime_id") == regime).iter_rows(named=True):
            name = f"{VARIANTS_TABLE}: variant {row['key']} breaches {cap['key']}"
            variant = int(row["variant_id"])
            pac = _year_columns(
                year_table(tables, SCALES_TABLE, "premium_allocation_rate"), variant
            )
            if (pac > cap["pac_max"]).any():
                messages.append(f"{name}: premium_allocation_rate above pac_max")
            first = pac[:5]
            if (first > 0).any() and (
                first.min() <= 0 or first.max() / first.min() > cap["pac_ratio_max_first5"]
            ):
                messages.append(
                    f"{name}: first-five-year allocation ratio above pac_ratio_max_first5"
                )
            admin = _year_columns(year_table(tables, SCALES_TABLE, "admin_charge_monthly"), variant)
            if (admin > cap["admin_max_monthly"]).any():
                messages.append(f"{name}: admin_charge_monthly above admin_max_monthly")
            for field, limit, above in (
                ("admin_escalation", "admin_escalation_max", True),
                ("guarantee_charge", "guarantee_charge_max", True),
                ("min_db_premium_multiple", "min_db_premium_multiple", False),
                ("lock_in_months", "lock_in_months_min", False),
            ):
                if (row[field] > cap[limit]) if above else (row[field] < cap[limit]):
                    side = "above" if above else "below"
                    messages.append(f"{name}: {field} {side} {limit}")
            for field in (r.name for r in features.DISC_CAP_FIELDS):
                charged = _year_columns(year_table(tables, SCALES_TABLE, field), variant)
                limit_values = _year_columns(year_table(tables, DISC_CAPS_TABLE, field), regime)
                years = min(len(charged), len(limit_values))
                if (
                    len(charged) > len(limit_values)
                    or (charged[:years] > limit_values[:years]).any()
                ):
                    messages.append(f"{name}: {field} above {DISC_CAPS_TABLE}")
    return messages


def check_policies_against_tables(
    policies: pl.DataFrame, holdings: pl.DataFrame, tables: Mapping[str, Table]
) -> list[str]:
    """Rules joining policy and holding rows to the fund universe, variants and caps.

    `holdings` holds exactly the rows of `policies` (already validated as raw rows)."""
    frames = keyed_frames(tables)
    funds, variants, caps = frames[FUNDS_TABLE], frames[VARIANTS_TABLE], frames[CAPS_TABLE]
    messages = []
    unknown_variants = policies.filter(
        ~pl.col("Product Variant").cast(pl.String).is_in(variants["key"].implode())
    )
    if unknown_variants.height:
        messages.append(
            f"{POLICY_TABLE}: Product Variant must exist in {VARIANTS_TABLE} "
            f"({unknown_variants.height} policy(ies))"
        )
    unknown_funds = holdings.filter(
        ~pl.col("Fund Code").cast(pl.String).is_in(funds["key"].implode())
    )
    if unknown_funds.height:
        codes = sorted(unknown_funds["Fund Code"].cast(pl.String).unique().to_list())[:5]
        messages.append(
            f"{HOLDINGS_TABLE}: Fund Code must exist in {FUNDS_TABLE} (exact match): {codes}"
        )
    if messages:
        return messages
    held = holdings.select(
        pl.col("Policy Number"),
        pl.col("Fund Code").cast(pl.String).alias("key"),
        numeric("Premium Allocation").alias("allocation"),
    ).join(funds.select("key", "fmc", "is_dpf", "selectable"), on="key", how="left")
    policy = (
        policies.select(
            pl.col("Policy Number"),
            pl.col("Product Variant").cast(pl.String).alias("variant"),
            numeric("Policy Status").alias("status"),
            numeric("Premium Frequency").alias("frequency"),
            numeric("Annualised Premium").alias("premium"),
            numeric("Sum Assured").alias("sum_assured"),
            numeric("Age at Policy Start").alias("age"),
        )
        .join(
            variants.select(pl.col("key").alias("variant"), "regime_id", "single_premium"),
            on="variant",
            how="left",
        )
        .join(caps.rename({"key": "regime"}), on="regime_id", how="left")
    )
    counts = held.group_by("Policy Number").agg(
        (pl.col("is_dpf") == 0).sum().alias("funds"),
        (pl.col("is_dpf") == 1).sum().alias("dpf"),
        pl.len().alias("rows"),
    )
    status = policy.join(counts, on="Policy Number", how="left")
    if (status["funds"] > MAX_FUND_SLOTS).any():
        messages.append(
            f"{HOLDINGS_TABLE}: a policy holds more than MAX_FUND_SLOTS ({MAX_FUND_SLOTS}) "
            "funds outside the DPF"
        )
    dpf = status["status"] == STATUS_DPF
    if (dpf & ((status["rows"] != 1) | (status["dpf"] != 1))).any():
        messages.append(
            f"{HOLDINGS_TABLE}: a Policy Status 1 policy holds exactly one row, in the DPF"
        )
    if (~dpf & (status["dpf"] > 0)).any():
        messages.append(f"{HOLDINGS_TABLE}: only Policy Status 1 policies hold the DPF")
    if ((held["selectable"] == 0) & (held["allocation"] != 0)).any():
        messages.append(f"{HOLDINGS_TABLE}: Premium Allocation must be 0 for non-selectable funds")
    capped = held.join(
        policy.select("Policy Number", "caps_apply", "fmc_max", "dpf_fmc_max"), on="Policy Number"
    )
    capped = capped.filter(pl.col("caps_apply") == 1)
    limit = pl.when(pl.col("is_dpf") == 1).then(pl.col("dpf_fmc_max")).otherwise(pl.col("fmc_max"))
    if capped.filter(pl.col("fmc") > limit).height:
        messages.append(f"{FUNDS_TABLE}: fmc of a fund held under a capped regime above its cap")
    regular = policy["single_premium"] == 0
    young = pl.Series(
        np.where(
            regular.to_numpy(),
            policy["age"].to_numpy() < policy["regular_age_threshold"].to_numpy(),
            policy["age"].to_numpy() < policy["single_age_threshold"].to_numpy(),
        )
    )
    minimum = np.select(
        [regular.to_numpy() & young.to_numpy(), regular.to_numpy(), young.to_numpy()],
        [
            policy["min_sa_multiple_regular_young"].to_numpy(),
            policy["min_sa_multiple_regular_old"].to_numpy(),
            policy["min_sa_multiple_single_young"].to_numpy(),
        ],
        policy["min_sa_multiple_single_old"].to_numpy(),
    )
    short = (policy["caps_apply"].to_numpy() == 1) & (
        policy["sum_assured"].to_numpy() < minimum * policy["premium"].to_numpy() * (1 - 1e-12)
    )
    if short.any():
        messages.append(
            f"{POLICY_TABLE}: Sum Assured below the regime's minimum multiple of the premium "
            f"for the entry age ({int(short.sum())} policy(ies))"
        )
    if ((policy["single_premium"] == 1) != (policy["frequency"] == 0)).any():
        messages.append(
            f"{POLICY_TABLE}: Premium Frequency 0 if and only if the variant is single premium"
        )
    return messages
