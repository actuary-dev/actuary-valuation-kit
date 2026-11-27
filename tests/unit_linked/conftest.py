"""A valid six-policy unit-linked book and the committed demo tables."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from avk.inputs.formats import FormatSpec, read
from avk.inputs.registry import BUILTIN_FORMATS
from avk.model.data import Axis
from avk.products.unit_linked import features

BASIS = Path(__file__).resolve().parents[2] / "examples/demo/basis"
VALUATION = date(2025, 12, 31)
RULE = Axis("binding", "int", 0, 0, "clamp", "clamp", (), None)


def load_tables(folder: Path = BASIS) -> dict:
    """The keyed and year tables as the run binds them (one field per year binding)."""

    def load(name, columns):
        spec = FormatSpec(name, {"path": name}, (RULE,), columns, "UNIT_LINKED", 480, "mixed")
        return read(BUILTIN_FORMATS[name], pl.read_csv(folder / f"{name}.csv"), spec)

    tables = {
        "ul_funds": load("ul_funds", tuple(r.name for r in features.FUND_FIELDS)),
        "ul_variants": load("ul_variants", tuple(r.name for r in features.VARIANT_FIELDS)),
        "ul_regulatory_caps": load(
            "ul_regulatory_caps", tuple(r.name for r in features.CAP_FIELDS)
        ),
        "ul_riy_caps": load("ul_riy_caps", ("riy_max",)),
    }
    for logical, rules in (
        ("ul_charge_scales", features.SCALE_FIELDS),
        ("ul_disc_charge_caps", features.DISC_CAP_FIELDS),
    ):
        for rule in rules:
            tables[f"{logical}/{rule.name}"] = load(logical, (rule.name,))
    return tables


def policy(number, variant, **fields):
    row = {
        "Policy Number": number,
        "Product Code": "UNIT_LINKED",
        "Product Variant": variant,
        "Valuation Date": "2025-12-31",
        "Policy Start Date": "2020-03-01",
        "Policy Term (Years)": 20,
        "Premium Payment Term (Years)": 20,
        "Premium Frequency": 1,
        "Annualised Premium": 100000.0,
        "Sum Assured": 1000000.0,
        "Distribution Channel": 0,
        "Currency": "INR",
        "Date of Birth": "1985-07-15",
        "Age at Policy Start": 34,
        "Gender": "M",
        "Smoking Status": "NS",
        "Underwriting Class": 0,
        "EMR": 1.0,
        "Flat Extra": 0.0,
        "Flat Extra Term (Years)": 0,
        "Policy Status": 0,
        "Status Date": "2020-03-01",
        "Paid Up Sum Assured": 0.0,
        "Date Of Last Premium Paid": "2025-03-01",
        "Premiums Paid To Date": 600000.0,
        "Instalments Paid": 6,
        "Premium Allocation Charges To Date": 23000.0,
        "Policy Administration Charges To Date": 13800.0,
        "Mortality Charges To Date": 9000.0,
        "Guarantee Charges To Date": 0.0,
        "Loyalty Additions To Date": 0.0,
        "Partial Withdrawals To Date": 0.0,
        "Withdrawals Current Policy Year": 0.0,
        "Withdrawals Previous Policy Year": 0.0,
        "Fund Value Sum Current Policy Year": 6500000.0,
        "Discontinuance Charge Paid": 0.0,
        "Portfolio": "UL_REGULAR",
        "Issue Cohort": 2020,
        "Profitability Group": 2,
        "Transition Approach": 2,
        "Measurement Model": "VFA",
        "Legal Entity": "DEMO_LIFE",
    }
    row.update(fields)
    return row


def holding(number, fund, units, allocation, **fields):
    row = {
        "Policy Number": number,
        "Product Code": "UNIT_LINKED",
        "Fund Code": fund,
        "Valuation Date": "2025-12-31",
        "Units": units,
        "Premium Allocation": allocation,
        "Fund Entry Date": "2020-03-01",
        "Premiums Allocated To Fund": 100000.0,
        "Units Allocated To Date": units * 1.1,
        "Units Cancelled To Date": units * 0.1,
        "Switches In To Date": 0.0,
        "Switches Out To Date": 0.0,
        "Guaranteed Unit Price": 0.0,
    }
    row.update(fields)
    return row


def valid_book() -> tuple[pl.DataFrame, pl.DataFrame]:
    """UL1 one fund; UL2 two funds, monthly; UL3 five funds, quarterly limited pay;
    UL4 discontinued in the DPF; UL5 reduced paid-up; UL6 single premium."""
    policies = [
        policy("UL1", "ULIP_CLASSIC"),
        policy("UL2", "ULIP_WEALTH_T2", **{"Premium Frequency": 12, "Instalments Paid": 70}),
        policy(
            "UL3",
            "ULIP_LIMITED_PAY_ROC",
            **{
                "Premium Frequency": 4,
                "Premium Payment Term (Years)": 10,
                "Instalments Paid": 24,
            },
        ),
        policy(
            "UL4",
            "ULIP_CLASSIC",
            **{
                "Policy Start Date": "2023-06-01",
                "Date of Birth": "1990-01-10",
                "Age at Policy Start": 33,
                "Policy Status": 1,
                "Status Date": "2025-03-01",
                "Premiums Paid To Date": 100000.0,
                "Instalments Paid": 1,
                "Issue Cohort": 2023,
                "Transition Approach": 2,
            },
        ),
        policy(
            "UL5",
            "ULIP_CLASSIC",
            **{
                "Policy Start Date": "2016-01-01",
                "Date of Birth": "1976-02-29",
                "Age at Policy Start": 39,
                "Policy Status": 2,
                "Status Date": "2022-05-01",
                "Paid Up Sum Assured": 300000.0,
                "Instalments Paid": 6,
                "Issue Cohort": 2016,
            },
        ),
        policy(
            "UL6",
            "ULIP_SINGLE",
            **{
                "Policy Term (Years)": 15,
                "Premium Payment Term (Years)": 0,
                "Premium Frequency": 0,
                "Annualised Premium": 500000.0,
                "Sum Assured": 625000.0,
                "Premiums Paid To Date": 500000.0,
                "Instalments Paid": 1,
            },
        ),
    ]
    holdings = [
        holding("UL1", "EQ_LARGE_CAP", 15000.0, 1.0),
        holding("UL2", "EQ_INDEX", 12000.0, 0.6),
        holding("UL2", "DT_GILT", 9000.0, 0.4),
        *(
            holding("UL3", fund, 1000.0 * (i + 1), share)
            for i, (fund, share) in enumerate(
                (
                    ("EQ_LARGE_CAP", 0.3),
                    ("EQ_MID_CAP", 0.2),
                    ("HY_BALANCED", 0.2),
                    ("DT_CORP_BOND", 0.2),
                    ("ALT_GOLD", 0.1),
                )
            )
        ),
        holding("UL4", "DPF", 5800.0, 0.0, **{"Premiums Allocated To Fund": 0.0}),
        holding("UL5", "EQ_FLEXI_CAP", 8000.0, 0.5),
        holding("UL5", "MM_LIQUID", 4000.0, 0.5),
        holding("UL6", "HY_BALANCED", 16000.0, 1.0, **{"Premiums Allocated To Fund": 500000.0}),
    ]
    return pl.DataFrame(policies), pl.DataFrame(holdings)


@pytest.fixture
def book():
    return valid_book()


@pytest.fixture(scope="session")
def ul_tables():
    return load_tables()
