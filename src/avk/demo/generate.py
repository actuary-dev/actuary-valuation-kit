"""Seeded vectorized demo books and reproducible, explicitly invented basis tables."""

import argparse
import json
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml  # type: ignore[import-untyped]

PRODUCTS = (
    "TERM",
    "ACCIDENTAL_DEATH_RIDER",
    "CRITICAL_ILLNESS_RIDER",
    "DISABILITY_RIDER",
    "CREDIT_LIFE",
)
POLICY_TABLES = (
    "policies_term",
    "policies_accidental_death",
    "policies_critical_illness",
    "policies_disability",
    "policies_credit_life",
)
HORIZON = 31
PARAMETERS = {
    "Inflation": 0.025,
    "Tax Rate": 0.20,
    "profit_transfer_rate": 0.015,
    "prudent_margin_mortality": 0.12,
    "prudent_margin_morbidity": 0.15,
    "prudent_margin_lapse": -0.10,
    "prudent_margin_expense": 0.10,
    "reserve_capital_factor": 0.035,
    "sum_at_risk_capital_factor": 0.002,
    "reserve_reinsurance_credit_floor": 0.5,
    "sum_at_risk_reinsurance_credit_floor": 0.5,
    "target_capital_ratio": 1.5,
    "Reinsurance Retention Limit abs": 60000.0,
    "Reinsurance Retention Limit proportion": 0.75,
    "Reserving Method": 1.0,
    "Use Male Mortality for Female": 0.0,
    "Setback in years": 0.0,
    "Operational Risk Charge - Earned Premium": 0.03,
    "Operational risk charge - Technical provisions": 0.004,
    "Cost of Capital Charge": 0.055,
    "Minimum SA Multiplier": 1.0,
    "Capital Expense Multiplier": 1.1,
    "Capital Expense Inflation Addition": 0.01,
    "Mass Lapse Stress Factor": 0.4,
    "Catastrophe Risk Factor": 0.0015,
    "Diversification Floor Factor": 0.0,
    "IFRS17 Multiplier Renewal Expenses": 1.0,
    "IFRS17 Addition Renewal Expenses": 0.0,
    "IFRS 17 RA Ratio": 0.08,
    "IFRS 17 RI RA Ratio": -0.05,
    "IFRS 17 stress expense": 1.1,
    "IFRS 17 stress inflation": 0.0,
    "IFRS17 Multiplier Initial Commission": 1.0,
    "ifrs_initial_expense_multiplier": 1.0,
    "Qx Mortality Proportion": 1.0,
    "Int rate to calculate PV of WOP": 0.04,
    "Max term for which UPR to be held (months)": 12.0,
    "flat_mortality_be": 0.0018,
    "flat_mortality_reserving": 0.0021,
}


def basis(folder: Path) -> dict[str, dict[str, str]]:
    """Write small tables from formulas specified in demo/README.md."""
    folder.mkdir(parents=True, exist_ok=True)
    locations: dict[str, dict[str, str]] = {}

    def put(name: str, rows: list[dict[str, Any]], fmt: str) -> None:
        path = folder / f"{name}.csv"
        pl.DataFrame(rows).write_csv(path)
        locations[name] = {"Path": str(path), "Format": f"avk_{fmt}_v1"}

    mortality = [
        {
            "age": age,
            "field": field,
            "value": min(0.7, 0.00012 + 0.00035 * np.exp(0.075 * (age - 35))) * sex,
        }
        for age in range(121)
        for field, sex in (("male", 1.0), ("female", 0.82), ("transgender", 0.91))
    ]
    for name in ("mortality", "reinsurance_mortality", "reinsurance_mortality_credit_life"):
        put(name, mortality, "mortality")
    morbidity = [
        {
            "age": age,
            "field": f"{risk}_{sex}",
            "value": min(0.4, base * np.exp(slope * (age - 35))) * factor,
        }
        for age in range(121)
        for risk, base, slope in (
            ("accidental_death", 0.00028, 0.008),
            ("critical_illness", 0.0011, 0.045),
            ("disability_rider", 0.00065, 0.035),
        )
        for sex, factor in (("male", 1.0), ("female", 0.9))
    ]
    for name in ("morbidity", "reinsurance_morbidity"):
        put(name, morbidity, "morbidity")
    put(
        "mortality_loadings_credit_life",
        [
            {"age": age, "field": f"{b}_{s}", "value": v}
            for age in range(121)
            for b in ("re", "be")
            for s, v in (("m_ns", 1.0), ("m_s", 1.3), ("f_ns", 0.82), ("f_s", 1.066))
        ],
        "mortality",
    )
    for name in ("mortality_loadings_term", "reinsurance_mortality_loadings_term"):
        put(
            name,
            [
                {
                    "lower": 0.0,
                    "upper": 1.0e12,
                    "smoker": smoker,
                    "value": 1.0 if smoker == 0 else 1.3,
                }
                for smoker in (0, 1)
            ],
            "bands",
        )
    for family in ("term", "credit_life"):
        put(
            f"lapse_rates_{family}",
            [
                {
                    "year": y,
                    "channel": c,
                    "value": (0.065 if y == 1 else 0.045 if y <= 3 else 0.025) + 0.005 * c,
                }
                for y in range(1, 33)
                for c in (0, 1)
            ],
            "lapse",
        )
        put(
            f"commissions_{family}",
            [
                {"year": y, "channel": c, "value": (0.10 if y == 1 else 0.025) + 0.005 * c}
                for y in range(1, 33)
                for c in (0, 1)
            ],
            "commission",
        )
    for family in ("term", "rider", "credit_life"):
        scale = 0.4 if family == "rider" else 1.0
        initial = [
            {"section": "initial", "index": sa, "field": field, "value": value}
            for sa in (0.0, 500000.0)
            for field, value in (
                ("sa", sa),
                ("of_prem", 0.04),
                ("fixed", 85.0 * scale),
                ("of_sa", 0.00015),
            )
        ]
        renewal = [
            {"section": "renewal", "index": 0.0, "field": field, "value": value}
            for field, value in (
                ("fixed_expenses", 24.0 * scale),
                ("claim_expenses", 0.0075),
                ("of_prem", 0.015),
            )
        ]
        put(f"expenses_{family}", initial + renewal, "expenses")
        if family != "credit_life":
            put(f"ifrs17_initial_expenses_{family}", initial, "expenses")
        put(
            f"ifrs17_renewal_expenses_{family}",
            [
                {"section": "schedule", "index": float(y), "field": field, "value": value}
                for y in range(1, 33)
                for field, value in (
                    ("fixed_expenses", 24.0 * scale),
                    ("claim_expenses", 0.0075),
                    ("of_prem", 0.015),
                )
            ],
            "expenses",
        )
    for name, fields in (
        ("interest_rates", (("roi", 0.04), ("vroi", 0.032), ("reference_forward_rates", 0.038))),
        (
            "ifrs17_interest_rates",
            (
                ("if17_current_roi", 0.037),
                ("if17_locked_in_rate", 0.035),
                ("if17_reference_forward_rates", 0.038),
            ),
        ),
    ):
        put(
            name,
            [
                {"year": y, "field": field, "value": rate}
                for y in range(1, 33)
                for field, rate in fields
            ],
            "curves",
        )
    put(
        "premium_frequency_factors",
        [
            {"frequency": freq, "field": product.lower(), "value": 1.0 / freq}
            for freq in (1, 2, 4, 12)
            for product in PRODUCTS
        ],
        "frequencies",
    )
    put(
        "product_parameters",
        [
            {"product": product, "parameter": key, "value": value}
            for product in PRODUCTS
            for key, value in {
                **PARAMETERS,
                "lapses_after_payment_term": float(product == "CREDIT_LIFE"),
                "renewal_premium_expense_after_payment_term": float(product == "CREDIT_LIFE"),
            }.items()
        ],
        "parameters",
    )
    pl.DataFrame(
        [
            {"cohort": str(cohort), "month": f"{y}-{m:02}", "value": (1.035 ** (1.0 / 12)) - 1}
            for cohort in (2023, 2024, 2025, 2026)
            for y in range(2023, 2058)
            for m in range(1, 13)
        ]
    ).write_csv(folder / "locked.csv")
    locations["locked"] = {"Path": str(folder / "locked.csv"), "Format": "avk_curves_v1"}
    return locations


def book(product: str, count: int, seed: int) -> pl.DataFrame:
    """Prefix-stable independent random streams, with no loop over policies."""
    if product not in PRODUCTS or count <= 0:
        raise ValueError("require a supported product and positive policy count")
    streams = [
        np.random.default_rng(s)
        for s in np.random.SeedSequence([seed, PRODUCTS.index(product)]).spawn(8)
    ]
    ages = streams[0].integers(24, 57, count)
    terms = (
        streams[1].integers(5, 21, count)
        if product == "CREDIT_LIFE"
        else streams[1].integers(10, 31, count)
    )
    pay_choice = np.arange(count) % 4
    pay_terms = np.where(
        pay_choice == 0, terms, np.minimum(terms, np.take([0, 5, 10, 20], pay_choice))
    )
    sa = streams[2].choice([80000.0, 140000.0, 240000.0], count)
    gender = streams[3].choice(["M", "F"], count)
    smoker = streams[4].choice(["NS", "S"], count, p=[0.8, 0.2])
    channel = streams[5].integers(0, 2, count)
    starts = streams[6].choice(
        ["2023-03-01", "2024-09-01", "2025-02-01", "2025-10-01", "2026-02-01"], count
    )
    # Two intentional premium levels provide profitable and onerous examples.
    cheap = streams[7].random(count) < 0.2
    rates = {
        "TERM": 0.006,
        "ACCIDENTAL_DEATH_RIDER": 0.0015,
        "CRITICAL_ILLNESS_RIDER": 0.004,
        "DISABILITY_RIDER": 0.003,
    }
    ids = np.char.add("DEMO", np.arange(count).astype(str))
    if product == "CREDIT_LIFE":
        loan_rate = 0.06
        monthly = loan_rate / 12
        emi = sa * monthly / (1 - (1 + monthly) ** (-terms * 12))
        return pl.DataFrame(
            {
                "Policy ID": ids,
                "Policy start date": starts,
                "Age at Policy Start": ages,
                "Policy Term (Years)": terms,
                "Loan Amount": sa,
                "EMI amount": emi,
                "Premium": sa * terms * np.where(cheap, 0.0002, 0.003),
                "Interest Rate": loan_rate,
                "Mode": 1,
                "Moratorium Period (months)": 0,
                "Interest Accrue": 0,
                "Reducing SA": 1,
                "Mortality Table Loading Flag": 0,
                "Distribution Channel": channel,
                "Gender": gender,
                "Smoker": smoker,
                "IFRS_Profitability": np.where(cheap, "onerous", "other"),
            }
        )
    premium = sa * rates[product] * terms / pay_terms * np.where(cheap, 0.12, 1.0)
    data = {
        "Policy Number": ids,
        "Policy Start Date": starts,
        "Policy Term (Years)": terms,
        "Premium Payment Term": pay_terms,
        "Age at Policy Start": ages,
        "Sum Assured": sa,
        "Premium Amount": premium,
        "Premium Frequency": 1,
        "Distribution Channel": channel,
        "Gender": gender,
        "Smoking Status": smoker,
        "Policy Status": 1,
        "IFRS_Profitability": np.where(cheap, "onerous", "other"),
    }
    if product.endswith("_RIDER"):
        data.update(
            {
                "Rider Premium": premium,
                "Base Premium": sa * 0.008,
                "Rider Option": PRODUCTS.index(product),
            }
        )
    return pl.DataFrame(data)


def stress(folder: Path, product: str) -> dict[str, Any]:
    # Convert the packaged stress preset, retaining its values and article citations.
    name = "solvency_ii_riders.yaml" if product.endswith("_RIDER") else "solvency_ii_life.yaml"
    preset = files("avk.presets").joinpath(name)
    values = yaml.safe_load(preset.read_text(encoding="utf-8"))
    rows = []
    for case in values["Cases"]:
        if "Factor" in case:
            shocks = {"none": {"Factor": case["Factor"]}}
        else:
            shocks = case["Shocks"]
        for target, windows in shocks.items():
            for shock in windows if isinstance(windows, list) else [windows]:
                end = shock.get("End_Month", 0)
                rows.append(
                    {
                        "risk": case["Risk"],
                        "target": target,
                        "method": "mass_lapse" if "Factor" in case else "revaluation",
                        "additive": shock.get("Additive", 0.0),
                        "multiplier": shock.get("Multiplicative", 1.0),
                        "start_month": shock.get("Start_Month", 0),
                        "end_month": HORIZON * 12 - 1 if end == "last" else end,
                        "maximum_decrease": shock.get("Maximum_Decrease", 1.0),
                        "factor": shock.get("Factor", 0.0),
                    }
                )
    pl.DataFrame(rows).write_csv(folder / "stresses.csv")
    pl.DataFrame(
        [
            {"risk": a, "other": b, "value": float(value)}
            for a, row in values["Correlation"].items()
            for b, value in row.items()
        ]
    ).write_csv(folder / "correlations.csv")
    (folder / "stress-source.yaml").write_text(preset.read_text(encoding="utf-8"))
    return {
        "Cases": {"CSV": str(folder / "stresses.csv"), "Format": "avk_stresses_v1"},
        "Correlation": {
            "CSV": str(folder / "correlations.csv"),
            "Format": "avk_correlations_v1",
        },
        "Settings": values["Settings"],
    }


def generate(folder: Path, product: str, count: int, seed: int) -> Path:
    """Generate inputs/configs; output paths always belong to the caller's folder."""
    folder = folder.resolve()
    locations = basis(folder / "basis")
    policies = book(product, count, seed)
    path = folder / "policies.csv"
    policies.write_csv(path)
    start = "Policy start date" if product == "CREDIT_LIFE" else "Policy Start Date"
    policies.filter(pl.col(start) <= "2025-12-31").write_csv(folder / "opening_policies.csv")
    term = pl.col("Policy Term (Years)")
    issue = pl.col(start).str.to_date()
    maturity = issue.dt.offset_by((term * 12).cast(pl.String) + "mo")
    policies.filter(maturity >= date(2026, 6, 30)).write_csv(folder / "closing_policies.csv")
    policy_table = POLICY_TABLES[PRODUCTS.index(product)]
    locations[policy_table] = {"Path": str(path)}
    pl.DataFrame(
        [
            {
                "product": product,
                "portfolio": product,
                "cohort": str(cohort),
                "profitability": bucket,
                "csm": 0.0 if bucket == "onerous" else 60000.0,
                "loss_component": 15000.0 if bucket == "onerous" else 0.0,
                "ri_csm": 0.0,
                "loss_recovery_component": 0.0,
            }
            for cohort in (2023, 2024, 2025)
            for bucket in ("onerous", "other")
            if policies.filter(
                (pl.col(start).str.starts_with(str(cohort)))
                & (pl.col("IFRS_Profitability") == bucket)
            ).height
        ]
    ).write_csv(folder / "balances.csv")
    locations["opening_balances"] = {
        "Path": str(folder / "balances.csv"),
        "Format": "avk_opening_v1",
    }
    cfg = {
        "Valuation_Date": "2025-12-31",
        "fiscal_start_month": 1,
        "Projection_Term": HORIZON,
        "Run_Type": "Valuation",
        "Products_to_run": [product],
        "Output_path": str(folder / "output/valuation"),
        "Output_seriatim_cf_flag": 0,
        "Batch_Size": 8192,
        "Inputs": {"Replace": locations},
    }

    def save(name: str, values: dict[str, Any]) -> Path:
        result = folder / f"{name}.json"
        result.write_text(json.dumps(values, indent=2) + "\n")
        return result

    result = save("valuation", cfg)
    save(
        "cases",
        {
            **cfg,
            "Output_path": str(folder / "output/cases"),
            "Cases": [
                {"Name": "mortality increase", "Shocks": {"mortality": {"Multiplicative": 1.15}}}
            ],
        },
    )
    save(
        "capital",
        {
            **cfg,
            "Run_Type": "StressCapital",
            "Output_path": str(folder / "output/capital"),
            "Stress_Set": stress(folder, product),
        },
    )
    ifrs = {
        "Reporting_Months": 6,
        "Locked_In_Curves": "locked",
        "Current_Curve": "ifrs_current",
        "Profitability_Field": "IFRS_Profitability",
        "RA_Method": "ratio",
        "RA_Ratio": 0.08,
        "RI_RA_Ratio": -0.05,
    }
    save(
        "measurement",
        {
            **cfg,
            "Run_Type": "IFRS17",
            "Output_path": str(folder / "output/measurement"),
            "IFRS17": ifrs,
        },
    )
    save(
        "rollforward",
        {
            **cfg,
            "Valuation_Date": "2026-06-30",
            "Run_Type": "IFRS17",
            "Output_path": str(folder / "output/rollforward"),
            "Inputs": {
                "Replace": {
                    **locations,
                    policy_table: {"Path": str(folder / "closing_policies.csv")},
                }
            },
            "IFRS17": {
                **ifrs,
                "Roll_Forward": {
                    "Opening": {
                        "Valuation_Date": "2025-12-31",
                        "Policy_Data": {policy_table: str(folder / "opening_policies.csv")},
                    },
                    "Opening_Balances": "opening_balances",
                },
            },
        },
    )
    return result


def _positive_count(raw: str) -> int:
    count = int(raw)
    if count <= 0:
        raise argparse.ArgumentTypeError("policy count must be positive")
    return count


def add_generate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("folder", type=Path)
    parser.add_argument("--product", required=True, choices=PRODUCTS)
    parser.add_argument("--count", type=_positive_count, default=10000)
    parser.add_argument("--seed", type=int, default=209)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_generate_arguments(parser)
    args = parser.parse_args()
    print(generate(args.folder, args.product, args.count, args.seed))


if __name__ == "__main__":
    main()
