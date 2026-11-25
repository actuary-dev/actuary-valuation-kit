import numpy as np
import polars as pl
import pytest

from avk.testing.parity import compare

BASE_PVFP = 21_309_663.46
CASE_PVFP = 21_310_108.49


@pytest.mark.parametrize(
    ("column", "case_pvfp", "expected_ok"),
    [
        ("MCEV_pvfp_BE_change_pct", np.nextafter(CASE_PVFP, np.inf), True),
        ("MCEV_pvfp_BE_change_pct", CASE_PVFP * (1 + 1e-9), False),
        ("ordinary_rate", np.nextafter(CASE_PVFP, np.inf), False),
    ],
    ids=["one-ulp", "one-part-per-billion", "ordinary-rate"],
)
def test_change_pct_parity(tmp_path, column, case_pvfp, expected_ok):
    golden = tmp_path / "golden.parquet"
    candidate = tmp_path / "candidate.parquet"
    golden_pct = (CASE_PVFP - BASE_PVFP) / BASE_PVFP * 100
    candidate_pct = (case_pvfp - BASE_PVFP) / BASE_PVFP * 100
    assert candidate_pct != golden_pct
    pl.DataFrame({column: [golden_pct]}).write_parquet(golden)
    pl.DataFrame({column: [candidate_pct]}).write_parquet(candidate)

    report = compare(candidate, golden, classes={column: "rate"})

    assert report.ok is expected_ok, report.to_markdown()
