"""Ingestion + validation tests: happy path, empty file, missing column, null values."""
from src.ingestion import SchemaError, ingest
from src.pipeline import run_pipeline
from src.validation import normalize_phone, validate_records
from tests.helpers import tmpdir, write_csv


def _validate(rows, **kw):
    with tmpdir() as d:
        return validate_records(ingest(write_csv(d, rows, **kw)))


def test_happy_path_valid_file():
    valid, rejected = _validate([["C1", "John Smith", "john@gmail.com", "9876543210"],
                                 ["C2", "Alice Johnson", "alice@gmail.com", "9999999999"]])
    assert len(valid) == 2 and len(rejected) == 0


def test_empty_file_zero_records():
    with tmpdir() as d:
        header_only = write_csv(d, [])
        assert len(ingest(header_only)) == 0
        zero_bytes = header_only.with_name("zero.csv")
        zero_bytes.write_text("")
        assert len(ingest(zero_bytes)) == 0
        summary = run_pipeline(header_only, f"{d}/out", f"{d}/logs")
        assert summary["input_count"] == 0 and summary["output_count"] == 0


def test_missing_column_rejects_file():
    with tmpdir() as d:
        path = write_csv(d, [["C1", "John", "9876543210"]], header=["customer_id", "name", "phone"])
        try:
            ingest(path)
        except SchemaError as exc:
            assert "email" in str(exc)
        else:
            raise AssertionError("SchemaError not raised")


def test_null_name_rejected():
    _, rejected = _validate([["C1", "", "a@gmail.com", "9876543210"]])
    assert rejected.iloc[0]["reason"] == "missing_name"


def test_null_email_rejected():
    _, rejected = _validate([["C1", "John", "", "9876543210"]])
    assert rejected.iloc[0]["reason"] == "missing_email"


def test_invalid_email_and_phone_rejected():
    _, rejected = _validate([["C1", "John", "not-an-email", "12345"]])
    assert set(rejected.iloc[0]["reason"].split(";")) == {"invalid_email", "invalid_phone"}


def test_null_phone_is_allowed():
    valid, rejected = _validate([["C1", "John", "john@gmail.com", ""]])
    assert len(valid) == 1 and len(rejected) == 0


def test_phone_normalisation():
    assert normalize_phone("+91 98765 43210") == "9876543210"
    assert normalize_phone("09876543210") == "9876543210"


def test_duplicate_customer_id_rejected():
    valid, rejected = _validate([["C1", "John", "a@gmail.com", "9876543210"],
                                 ["C1", "Jane", "b@gmail.com", "9876543211"]])
    assert len(valid) == 1 and rejected.iloc[0]["reason"] == "duplicate_customer_id"
