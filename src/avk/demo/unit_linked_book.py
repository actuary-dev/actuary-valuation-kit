"""Invented unit-linked demo book: policies, fund holdings and the Valuation run file.

Vectorised over policies with prefix-stable seeded streams from SeedSequence([seed, 5]).
History fields are approximate invented values, consistent in sign and order only.
"""

import json
from pathlib import Path

import numpy as np
import polars as pl

from avk.demo.unit_linked import DPF_CODE, FUNDS
from avk.products.unit_linked.bindings import CODE, HOLDINGS_TABLE, POLICY_TABLE

VALUATION = "2025-12-31"
FIRST_YEAR = 2006  # starts are monthly from 2006-01 to 2025-12
START_MONTHS = 240
REGULAR_VARIANTS = ("ULIP_CLASSIC", "ULIP_WEALTH_T2", "ULIP_MATURITY_GUARANTEE")
LIMITED_VARIANTS = ("ULIP_LIMITED_PAY_ROC", "ULIP_CLASSIC")
SINGLE_VARIANTS = ("ULIP_SINGLE", "UL_INVESTMENT_BOND")
PORTFOLIOS = {
    "ULIP_CLASSIC": "UL_REGULAR",
    "ULIP_WEALTH_T2": "UL_REGULAR",
    "ULIP_MATURITY_GUARANTEE": "UL_GUARANTEED",
    "ULIP_LIMITED_PAY_ROC": "UL_LIMITED",
    "ULIP_SINGLE": "UL_SINGLE",
    "UL_INVESTMENT_BOND": "UL_SINGLE",
}
FUND_COUNTS = ([1, 2, 3, 4, 5], [0.30, 0.35, 0.20, 0.10, 0.05])


def _dates(index: np.ndarray) -> np.ndarray:
    """First-of-month ISO dates for month indices counted from 2006-01."""
    years = FIRST_YEAR + index // 12
    months = index % 12 + 1
    return np.char.add(
        np.char.add(np.char.zfill(years.astype(str), 4), "-"),
        np.char.add(np.char.zfill(months.astype(str), 2), "-01"),
    )


def ul_book(count: int, seed: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Invented unit-linked policies and their fund holdings."""
    if count <= 0:
        raise ValueError("require a positive policy count")
    rng = [np.random.default_rng(s) for s in np.random.SeedSequence([seed, 5]).spawn(20)]
    ages = rng[0].integers(18, 61, count)
    terms = np.minimum(rng[1].integers(10, 31, count), 75 - ages)
    kind = rng[2].choice(3, count, p=[0.60, 0.25, 0.15])  # regular, limited, single
    variant = np.where(
        kind == 0,
        np.take(REGULAR_VARIANTS, rng[3].choice(3, count, p=[0.45, 0.30, 0.25])),
        np.where(
            kind == 1,
            np.take(LIMITED_VARIANTS, rng[4].choice(2, count, p=[0.6, 0.4])),
            np.take(SINGLE_VARIANTS, rng[5].choice(2, count)),
        ),
    )
    single = kind == 2
    frequency = np.where(single, 0, rng[6].choice([1, 2, 4, 12], count))
    ppt = np.where(kind == 0, terms, np.where(kind == 1, rng[7].choice([5, 7, 10], count), 0))
    low, high = np.where(single, 1e5, 48000.0), np.where(single, 2e6, 600000.0)
    premium = np.round(np.exp(rng[8].uniform(np.log(low), np.log(high))), -3)
    regular_multiple = np.where(
        ages < 50,
        rng[9].choice([7.0, 10.0, 15.0, 20.0], count),
        rng[9].choice([5.0, 7.0], count),
    )
    regular_multiple = np.where((ages > 45) & (regular_multiple == 20.0), 15.0, regular_multiple)
    multiple = np.where(
        variant == "UL_INVESTMENT_BOND",
        1.01,
        np.where(single, np.where(ages < 45, 1.25, 1.10), regular_multiple),
    )
    sum_assured = np.round(multiple * premium, 2)
    # Start month (from 2006-01) late enough that the term has not ended.
    lowest = np.maximum(0, START_MONTHS - 12 * terms)
    start = lowest + np.floor(rng[10].random(count) * (START_MONTHS - lowest)).astype(np.int64)
    duration = START_MONTHS - start  # the policy month at the valuation date, 1 to 240
    start_year = FIRST_YEAR + start // 12
    lock_in = np.where(variant == "UL_INVESTMENT_BOND", 0, 60)
    draw = rng[11].random(count)
    dpf = ~single & (lock_in > 0) & (duration <= lock_in) & (duration >= 2) & (draw < 0.12)
    rpu = ~single & (duration > 62) & (draw < 0.08)
    status = np.where(dpf, 1, np.where(rpu, 2, 0))
    # The month premiums stopped: inside the lock-in for status 1, within the 36-month
    # revival period after the lock-in for status 2.
    earliest = np.where(dpf, 1, np.maximum(61, duration - 35))
    span = np.maximum(duration - earliest, 1)
    stop = earliest + np.floor(rng[12].random(count) * span).astype(np.int64)
    gap = np.where(single, 12, 12 // np.maximum(frequency, 1))
    payable = np.where(single, 1, frequency * ppt)
    months_paid = np.where(status == 0, np.minimum(duration, ppt * 12), stop)
    instalments = np.where(single, 1, np.minimum(-(-months_paid // gap), payable))
    instalment = np.where(single, premium, premium / np.maximum(frequency, 1))
    paid = np.round(instalments * instalment, 2)
    paid_up = np.where(status == 2, np.round(sum_assured * instalments / payable, 2), 0.0)
    years = (duration - 1) // 12 + 1
    value = np.round(paid * 0.9 * 1.07 ** (duration / 24.0), 2)
    since = (duration - 1) % 12 + 1
    charged_months = np.where(status == 0, duration, stop)
    rated = rng[13].random(count) < 0.1
    start_dates = _dates(start)
    policies = pl.DataFrame(
        {
            "Policy Number": np.char.add(
                "UL", np.char.zfill(np.arange(1, count + 1).astype(str), 7)
            ),
            "Product Code": CODE,
            "Product Variant": variant,
            "Valuation Date": VALUATION,
            "Policy Start Date": start_dates,
            "Policy Term (Years)": terms,
            "Premium Payment Term (Years)": ppt,
            "Premium Frequency": frequency,
            "Annualised Premium": premium,
            "Sum Assured": sum_assured,
            "Distribution Channel": rng[14].integers(0, 2, count),
            "Currency": "INR",
            "_age": ages,
            "_days": rng[15].integers(1, 360, count),
            "Gender": rng[16].choice(["M", "F", "T"], count, p=[0.50, 0.48, 0.02]),
            "Smoking Status": rng[17].choice(["NS", "S"], count, p=[0.8, 0.2]),
            "Underwriting Class": rated.astype(np.int64),
            "EMR": np.where(rated, 1.5, 1.0),
            "Flat Extra": np.where(rated, 2.0, 0.0),
            "Flat Extra Term (Years)": np.where(rated, 5, 0),
            "Policy Status": status,
            "Status Date": np.where(status == 0, start_dates, _dates(start + stop)),
            "Paid Up Sum Assured": paid_up,
            "Date Of Last Premium Paid": _dates(start + (instalments - 1) * gap),
            "Premiums Paid To Date": paid,
            "Instalments Paid": instalments,
            "Premium Allocation Charges To Date": np.round(paid * 0.04, 2),
            "Policy Administration Charges To Date": 200.0 * charged_months,
            "Mortality Charges To Date": np.round(paid * 0.02, 2),
            "Guarantee Charges To Date": np.where(
                variant == "ULIP_MATURITY_GUARANTEE", np.round(value * 0.004 * years, 2), 0.0
            ),
            "Loyalty Additions To Date": np.where(
                np.isin(variant, ("ULIP_CLASSIC", "ULIP_WEALTH_T2")) & (years > 10),
                np.round(value * 0.003 * (years - 10), 2),
                0.0,
            ),
            "Partial Withdrawals To Date": np.where(
                years > 6, np.round(value * 0.006 * (years - 6), 2), 0.0
            ),
            "Withdrawals Current Policy Year": np.where(
                years > 6, np.round(value * 0.006 * since / 12, 2), 0.0
            ),
            "Withdrawals Previous Policy Year": np.where(
                years > 7, np.round(value * 0.006, 2), 0.0
            ),
            "Fund Value Sum Current Policy Year": np.round(value * since, 2),
            "Discontinuance Charge Paid": np.where(
                dpf, np.minimum(np.round(0.04 * premium, 2), 5000.0), 0.0
            ),
            "Portfolio": np.vectorize(PORTFOLIOS.get, otypes=[str])(variant),
            "Issue Cohort": start_year,
            "Profitability Group": rng[18].choice(3, count, p=[0.1, 0.3, 0.6]),
            "Transition Approach": np.where(start_year < 2023, 2, 0),
            "Measurement Model": "VFA",
            "Legal Entity": "DEMO_LIFE",
        }
    )
    begin = pl.col("Policy Start Date").str.to_date()
    born = begin.dt.offset_by(pl.format("-{}y", pl.col("_age"))) - pl.duration(days=pl.col("_days"))
    policies = policies.with_columns(born.alias("_born")).with_columns(
        pl.col("_born").cast(pl.String).alias("Date of Birth"),
        (
            begin.dt.year()
            - pl.col("_born").dt.year()
            - (
                (begin.dt.month() < pl.col("_born").dt.month())
                | (
                    (begin.dt.month() == pl.col("_born").dt.month())
                    & (begin.dt.day() < pl.col("_born").dt.day())
                )
            ).cast(pl.Int32)
        )
        .cast(pl.Int64)
        .alias("Age at Policy Start"),
    )
    columns = [c for c in policies.columns if not c.startswith("_")]
    columns.remove("Date of Birth")
    columns.remove("Age at Policy Start")
    after = columns.index("Currency") + 1
    columns[after:after] = ["Date of Birth", "Age at Policy Start"]
    policies = policies.select(columns)
    return policies, _holdings(policies, rng[19], value, paid, status)


def _holdings(
    policies: pl.DataFrame,
    rng: np.random.Generator,
    value: np.ndarray,
    paid: np.ndarray,
    status: np.ndarray,
) -> pl.DataFrame:
    """One to five selectable funds per policy; a status-1 policy holds the DPF alone."""
    count = policies.height
    selectable = [f for f in FUNDS if f[0] != DPF_CODE]
    codes = np.array([f[0] for f in selectable])
    prices = np.array([f[2] for f in selectable])
    guaranteed = np.array([f[4] > 0 for f in selectable])
    held = rng.choice(FUND_COUNTS[0], count, p=FUND_COUNTS[1])
    chosen = np.argsort(rng.random((count, len(selectable))), axis=1)[:, :5]
    present = np.arange(5)[None, :] < held[:, None]
    weights = rng.gamma(1.0, size=(count, 5)) * present
    shares = weights / weights.sum(axis=1, keepdims=True)
    # Whole percentages, at least 1 each, adjusted to sum exactly to 100.
    percent = present * (1 + np.floor(shares * (100 - held[:, None])))
    percent[:, 0] += 100 - percent.sum(axis=1)
    allocation = percent / 100.0
    price = prices[chosen]
    units = np.round(value[:, None] * allocation / price, 4)
    rows = np.nonzero(present & (status[:, None] != 1))
    numbers = policies["Policy Number"].to_numpy()
    entries = policies["Policy Start Date"].to_numpy()
    dpf_price = next(f[2] for f in FUNDS if f[0] == DPF_CODE)
    dpf = np.nonzero(status == 1)[0]
    funds = pl.DataFrame(
        {
            "_i": rows[0],
            "_k": rows[1],
            "Policy Number": numbers[rows[0]],
            "Fund Code": codes[chosen][rows],
            "Units": units[rows],
            "Premium Allocation": allocation[rows],
            "Fund Entry Date": entries[rows[0]],
            "Premiums Allocated To Fund": np.round(paid[rows[0]] * 0.96 * allocation[rows], 2),
            "Guaranteed Unit Price": np.where(
                guaranteed[chosen][rows], np.round(price[rows] * 1.05, 4), 0.0
            ),
        }
    )
    discontinued = pl.DataFrame(
        {
            "_i": dpf,
            "_k": np.zeros(len(dpf), dtype=np.int64),
            "Policy Number": numbers[dpf],
            "Fund Code": np.full(len(dpf), DPF_CODE),
            "Units": np.round(value[dpf] * 0.97 / dpf_price, 4),
            "Premium Allocation": np.zeros(len(dpf)),
            "Fund Entry Date": entries[dpf],
            "Premiums Allocated To Fund": np.zeros(len(dpf)),
            "Guaranteed Unit Price": np.zeros(len(dpf)),
        }
    )
    allocated = (pl.col("Units") * 1.15).round(4)
    return (
        pl.concat([funds, discontinued], how="vertical_relaxed")
        .sort("_i", "_k")
        .select(
            "Policy Number",
            pl.lit(CODE).alias("Product Code"),
            "Fund Code",
            pl.lit(VALUATION).alias("Valuation Date"),
            "Units",
            "Premium Allocation",
            "Fund Entry Date",
            "Premiums Allocated To Fund",
            allocated.alias("Units Allocated To Date"),
            (allocated - pl.col("Units")).round(4).alias("Units Cancelled To Date"),
            pl.lit(0.0).alias("Switches In To Date"),
            pl.lit(0.0).alias("Switches Out To Date"),
            "Guaranteed Unit Price",
        )
    )


def generate_ul(
    folder: Path, count: int, seed: int, locations: dict[str, dict[str, str]], horizon: int
) -> Path:
    """Write the book, the holdings and a Valuation run file (UNIT_LINKED's only run type)."""
    policies, holdings = ul_book(count, seed)
    policies.write_csv(folder / "policies.csv")
    holdings.write_csv(folder / "policy_funds.csv")
    config = {
        "Valuation_Date": VALUATION,
        "fiscal_start_month": 1,
        "Projection_Term": horizon,
        "Run_Type": "Valuation",
        "Products_to_run": [CODE],
        "Output_path": str(folder / "output/valuation"),
        "Output_seriatim_cf_flag": 0,
        "Batch_Size": 8192,
        "Inputs": {
            "Replace": {
                **locations,
                POLICY_TABLE: {"Path": str(folder / "policies.csv")},
                HOLDINGS_TABLE: {"Path": str(folder / "policy_funds.csv")},
            }
        },
    }
    result = folder / "valuation.json"
    result.write_text(json.dumps(config, indent=2) + "\n")
    return result
