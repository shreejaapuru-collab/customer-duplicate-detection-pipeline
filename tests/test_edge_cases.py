"""Edge cases from the brief: schema change, partial failure + retry, out-of-order input,
and domain-specific duplicate scenarios."""
import hashlib
import random
from pathlib import Path

import pandas as pd

import src.pipeline as pipeline_module
from src.ingestion import SchemaError, ingest
from src.pipeline import run_pipeline
from tests.helpers import tmpdir, write_csv


def _run(rows, header=None, d=None):
    kw = {"header": header} if header else {}
    path = write_csv(d, rows, **kw)
    return run_pipeline(path, f"{d}/out", f"{d}/logs"), Path(d, "out")


def _masters(out):
    return pd.read_csv(out / "merged_records.csv", dtype=str, keep_default_na=False)


# ---------- schema change ----------
def test_unexpected_extra_column_is_tolerated():
    with tmpdir() as d:
        path = write_csv(d, [["C1", "John Smith", "john@gmail.com", "9876543210", "gold"]],
                         header=["customer_id", "name", "email", "phone", "loyalty_tier"])
        df = ingest(path)
        assert "loyalty_tier" not in df.columns and len(df) == 1


def test_renamed_column_rejects_file_and_records_reason():
    with tmpdir() as d:
        path = write_csv(d, [["C1", "John", "a@gmail.com", "9876543210"]],
                         header=["customer_id", "name", "e_mail", "phone"])
        try:
            run_pipeline(path, f"{d}/out", f"{d}/logs")
        except SchemaError:
            pass
        else:
            raise AssertionError("expected SchemaError")
        metrics = pd.read_csv(f"{d}/out/run_metrics.csv", dtype=str, keep_default_na=False)
        assert metrics.iloc[0]["status"] == "FILE_REJECTED" and "email" in metrics.iloc[0]["failure_reason"]


# ---------- partial failure + retry, rerun ----------
def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_partial_failure_keeps_old_outputs_and_retry_succeeds():
    sample = Path("data/sample/customers.csv")
    with tmpdir() as d:
        out = Path(d, "out")
        run_pipeline(sample, out, f"{d}/logs")
        before = _digest(out / "merged_records.csv")

        original = pipeline_module.publish_outputs
        def boom(*args, **kwargs):
            raise RuntimeError("disk full (simulated)")
        pipeline_module.publish_outputs = boom
        try:
            run_pipeline(sample, out, f"{d}/logs")
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected simulated failure")
        finally:
            pipeline_module.publish_outputs = original

        metrics = pd.read_csv(out / "run_metrics.csv", dtype=str, keep_default_na=False)
        assert metrics.iloc[0]["status"] == "FAILED" and "disk full" in metrics.iloc[0]["failure_reason"]
        assert _digest(out / "merged_records.csv") == before          # old outputs untouched

        run_pipeline(sample, out, f"{d}/logs")                          # retry = just rerun
        metrics = pd.read_csv(out / "run_metrics.csv", dtype=str, keep_default_na=False)
        assert len(metrics) == 1 and metrics.iloc[0]["status"] == "SUCCESS"
        assert _digest(out / "merged_records.csv") == before


# ---------- out-of-order input ----------
def test_row_order_does_not_change_output():
    rows = [["C001", "John Smith", "john@gmail.com", "9876543210"],
            ["C002", "Jon Smith", "john@gmail.com", "9876543210"],
            ["C003", "Alice Johnson", "alice@gmail.com", "9999999999"],
            ["C004", "John Smyth", "jsmyth@outlook.com", "9000000002"]]
    shuffled = rows[:]
    random.Random(1).shuffle(shuffled)
    with tmpdir() as d1, tmpdir() as d2:
        _, out1 = _run(rows, d=d1)
        _, out2 = _run(shuffled, d=d2)
        a = _masters(out1).drop(columns=["run_id"])
        b = _masters(out2).drop(columns=["run_id"])
        assert a.equals(b)
        assert (out1 / "review_queue.csv").read_text() == (out2 / "review_queue.csv").read_text()


# ---------- domain-specific edge cases ----------
def test_transitive_chain_becomes_one_master():
    # A~B share email, B~C share phone, A and C share nothing directly
    with tmpdir() as d:
        s, out = _run([["C1", "John Smith", "j1@gmail.com", "9000000001"],
                       ["C2", "Jon Smith", "j1@gmail.com", "9000000002"],
                       ["C3", "Jon Smith", "j3@gmail.com", "9000000002"]], d=d)
        m = _masters(out)
        assert len(m) == 1 and m.iloc[0]["source_ids"] == "C1|C2|C3"


def test_shared_family_phone_different_people_not_merged():
    with tmpdir() as d:
        s, out = _run([["C1", "Ravi Kumar", "ravi@gmail.com", "9000000001"],
                       ["C2", "Sita Kumar", "sita@gmail.com", "9000000001"]], d=d)
        assert s["output_count"] == 2 and s["review_pairs"] == 0


def test_same_name_different_people_goes_to_review_not_merged():
    with tmpdir() as d:
        s, out = _run([["C1", "Rahul Sharma", "rahul.a@gmail.com", "9000000001"],
                       ["C2", "Rahul Sharma", "rahul.b@gmail.com", "9000000002"]], d=d)
        assert s["output_count"] == 2 and s["review_pairs"] == 1


def test_email_case_phone_format_differences_are_normalised():
    with tmpdir() as d:
        s, out = _run([["C1", "John Smith", "John@Gmail.com ", "+91 98765 43210"],
                       ["C2", "john smith", "john@gmail.com", "9876543210"]], d=d)
        assert s["output_count"] == 1


def test_rejected_records_are_traceable_to_source_row():
    with tmpdir() as d:
        s, out = _run([["C1", "John Smith", "john@gmail.com", "9876543210"],
                       ["C2", "", "x@gmail.com", "9876543211"]], d=d)
        rej = pd.read_csv(out / "rejected_records.csv", dtype=str, keep_default_na=False)
        assert rej.iloc[0]["record_id"] == "C2" and rej.iloc[0]["source_row"] == "3"
        assert rej.iloc[0]["source_file"] == "customers.csv" and rej.iloc[0]["run_id"] == s["run_id"]


def test_reconciliation_report_all_pass_on_sample():
    with tmpdir() as d:
        s = run_pipeline("data/sample/customers.csv", f"{d}/out", f"{d}/logs")
        rec = pd.read_csv(f"{d}/out/reconciliation_report.csv")
        assert (rec["status"] == "PASS").all() and s["reconciliation_failures"] == 0
