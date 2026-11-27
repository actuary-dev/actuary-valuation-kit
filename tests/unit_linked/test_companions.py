"""The product-generic companion policy table hook of the run layer."""

import json

import polars as pl
import pytest

from avk.demo.generate import generate
from avk.inputs.sources import ResolvedInputs
from avk.inputs.validation import Issue
from avk.products.term.factory import TermFactory
from avk.products.term.preparation import TermModelPointAdapter
from avk.products.term.validation import TermPolicyValidator
from avk.runs import check as check_module
from avk.runtime.errors import InputError

SEEN: list[pl.DataFrame] = []


class RecordingAdapter(TermModelPointAdapter):
    def __init__(self, companion, *args):
        super().__init__(*args)
        self.companion = companion

    def prepare(self, frame, config):
        SEEN.append(self.companion)
        return super().prepare(frame, config)


class CompanionValidator(TermPolicyValidator):
    def __init__(self, code, messages=()):
        super().__init__(code)
        self.messages = messages

    def validate_companions(self, policies, companions, valuation_date):
        assert set(companions) == {"extra_rows"}
        return [Issue("error", m) for m in self.messages]

    def companion_orphans(self, known, companions):
        rows = companions["extra_rows"]
        missing = rows.filter(~known(rows["Policy Number"]))
        return (
            [Issue("error", f"extra_rows: {missing.height} row(s) without a policy")]
            if missing.height
            else []
        )


class CompanionFactory(TermFactory):
    companion_tables = ("extra_rows",)
    messages: tuple[str, ...] = ()

    def companion_adapter(self, tables, companions):
        return RecordingAdapter(
            companions["extra_rows"],
            self.code,
            self.policy_table,
            tables,
            self.definition_class.FIELDS,
        )

    def validator(self):
        return CompanionValidator(self.code, self.messages)


@pytest.fixture
def run(tmp_path, monkeypatch):
    SEEN.clear()
    config = generate(tmp_path, "TERM", 24, 209)
    ids = pl.read_csv(tmp_path / "policies.csv")["Policy Number"]
    extra = tmp_path / "extra.csv"
    pl.DataFrame({"Policy Number": ids, "value": range(len(ids))}).write_csv(extra)
    cfg = json.loads(config.read_text())
    cfg["Inputs"]["Replace"]["extra_rows"] = {"Path": str(extra)}
    config.write_text(json.dumps(cfg))
    factory = CompanionFactory()
    monkeypatch.setattr(check_module, "run_factory", lambda cfg: factory)
    reads: list[str] = []
    original = ResolvedInputs.read

    def counting(self, name):
        reads.append(name)
        return original(self, name)

    monkeypatch.setattr(ResolvedInputs, "read", counting)
    return {"config": config, "factory": factory, "reads": reads, "folder": tmp_path}


def test_companion_read_once_and_given_to_adapter(run):
    report = check_module.check(run["config"])
    assert run["reads"].count("extra_rows") == 1
    assert len(SEEN) == 1
    assert SEEN[0]["value"].to_list() == list(range(24))
    assert report.points is not None and report.points.frame.height == 24


def test_companion_issues_raise_one_error(run):
    run["factory"].messages = ("extra_rows: first rule", "extra_rows: second rule")
    with pytest.raises(InputError) as info:
        check_module.check(run["config"])
    assert str(info.value) == "extra_rows: first rule\nextra_rows: second rule"
    assert SEEN == []


def test_companion_orphans_raise(run):
    extra = run["folder"] / "extra.csv"
    frame = pl.read_csv(extra)
    pl.concat([frame, pl.DataFrame({"Policy Number": ["NOPE"], "value": [99]})]).write_csv(extra)
    with pytest.raises(InputError, match="extra_rows: 1 row"):
        check_module.check(run["config"])


def streamed(run, rows):
    folder = run["folder"]
    pl.read_csv(folder / "policies.csv").write_parquet(folder / "policies.parquet")
    if rows is not None:
        rows.write_csv(folder / "extra.csv")
    cfg = json.loads(run["config"].read_text())
    cfg["Batch_Size"] = 10
    cfg["Inputs"]["Replace"]["policies_term"] = {
        "Source": "parquet",
        "Path": str(folder / "policies.parquet"),
    }
    run["config"].write_text(json.dumps(cfg))


def test_streamed_batches_share_the_companion(run):
    streamed(run, None)
    report = check_module.check(run["config"])
    assert report.streamed_policies
    assert run["reads"].count("extra_rows") == 1
    assert len(SEEN) == 3
    assert all(frame is SEEN[0] for frame in SEEN)


def test_streamed_orphan_reported_once_after_all_batches(run):
    frame = pl.read_csv(run["folder"] / "extra.csv")
    orphans = pl.DataFrame({"Policy Number": ["NOPE1", "NOPE2"], "value": [98, 99]})
    streamed(run, pl.concat([frame, orphans]))
    with pytest.raises(InputError) as info:
        check_module.check(run["config"])
    assert str(info.value) == "extra_rows: 2 row(s) without a policy"
    assert len(SEEN) == 3  # every batch prepared before the orphans are known


def test_existing_factories_declare_no_companions():
    from avk.products.registry import ProductRegistry

    registry = ProductRegistry.default()
    for code in ("TERM", "ACCIDENTAL_DEATH_RIDER", "CREDIT_LIFE"):
        assert registry.for_code(code).companion_tables == ()
