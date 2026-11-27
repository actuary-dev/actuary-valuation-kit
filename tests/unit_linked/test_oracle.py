"""Reconcile the per-policy-month valuation output with the independent scalar oracle."""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from avk.demo.generate import generate
from avk.products.registry import ProductRegistry
from avk.testing.parity import compare

sys.path.insert(0, str(Path(__file__).parent))
import oracle  # noqa: E402


@pytest.fixture(scope="module")
def reconciled(tmp_path_factory, oracle_policies):
    from avk.api import run

    path = generate(tmp_path_factory.mktemp("ul-oracle"), "UNIT_LINKED", 6, 209)
    policies, holdings = oracle_policies
    policies.write_csv(path.parent / "policies.csv")
    holdings.write_csv(path.parent / "policy_funds.csv")
    config = json.loads(path.read_text())
    config["Output_seriatim_cf_flag"] = 1
    path.write_text(json.dumps(config))
    run(path)
    output = path.parent / "output" / "valuation"
    detail = pl.read_csv(output / "UNIT_LINKED_Base_output.csv", infer_schema_length=None)
    horizon = detail.filter(pl.col("Policy_Number") == detail["Policy_Number"][0]).height
    basis = oracle.Basis.read(path.parent / "basis")
    valuation = date.fromisoformat(config["Valuation_Date"])
    results = {}
    for row in policies.iter_rows(named=True):
        rows = [
            h for h in holdings.iter_rows(named=True) if h["Policy Number"] == row["Policy Number"]
        ]
        policy = oracle.Policy.prepare(row, rows, basis, valuation)
        results[row["Policy Number"]] = oracle.project(policy, basis, horizon)
    return detail, results, horizon, output


def oracle_frame(detail, results, schema):
    numbers = detail["Policy_Number"].unique(maintain_order=True).to_list()
    columns = {
        "Policy_Number": detail["Policy_Number"],
        "Projection_Step": detail["Projection_Step"],
    }
    for name, column, basis in schema.entries:
        values = []
        for number in numbers:
            data = results[number]
            source = data[basis].get(column)
            values.extend(data[None][column] if source is None else source)
        # The writer leaves a NaN cell empty (0 / 0 after the last exit).
        columns[name] = [None if value != value else value for value in values]
    return pl.DataFrame(columns)


def test_oracle_reconciles_every_output_column(reconciled, tmp_path):
    detail, results, _, _ = reconciled
    schema = ProductRegistry.default().for_code("UNIT_LINKED").output_schema("Valuation")
    golden = oracle_frame(detail, results, schema)
    candidate = detail.select(golden.columns)
    candidate.write_parquet(tmp_path / "model.parquet")
    golden.write_parquet(tmp_path / "oracle.parquet")
    classes = {"Policy_Number": "identifier", "Projection_Step": "identifier"}
    for name in golden.columns[2:]:
        classes[name] = "decrement" if name.startswith("decrements_") else "value"
    report = compare(tmp_path / "model.parquet", tmp_path / "oracle.parquet", classes=classes)
    assert len(report.columns) == len(schema.entries) + 2
    report.assert_ok()


def test_oracle_book_exercises_the_features(reconciled):
    _, results, _, _ = reconciled
    be = {number: data["be"] for number, data in results.items()}
    assert max(be["O1"]["addition_outgo"]) > 0
    assert max(be["O2"]["partial_withdrawal_outgo"]) > 0
    assert max(be["O3"]["dpf_lockin_paid"]) > 0 and be["O3"]["D_begin"][1] == 1
    assert be["O4"]["R_begin"][1] == 1 and max(be["O4"]["expiries_R"]) > 0
    assert be["O5"]["maturity_guarantee_A"][1] > 0
    assert max(be["O6"]["return_of_charges"]) > 0
    reserving = results["O1"]["reserving"]
    assert reserving["gf_reserve_dcf"][0] < 0 < reserving["gf_reserve_held"][0]


def test_seriatim_matches_the_oracle_at_step_zero(reconciled):
    _, results, _, output = reconciled
    seriatim = pl.read_csv(output / "UNIT_LINKED_Base_seriatim_output.csv")
    for row in seriatim.iter_rows(named=True):
        data = results[row["Policy_Number"]]
        expected = {
            "cashflows_unit_reserve_reserving": data["reserving"]["unit_reserve"][0],
            "cashflows_total_reserve_reserving": data["reserving"]["total_reserve"][0],
            "MCEV_bel_MC": data[None]["bel"][0],
            "MCEV_vif_MC": data[None]["vif"][0],
            "cashflows_sum_at_risk_BE": data["be"]["sum_at_risk"][0],
        }
        for name, value in expected.items():
            assert row[name] == pytest.approx(value, rel=1e-6, abs=1e-5), name
        assert np.isfinite(list(expected.values())).all()
