"""Duplicate detection, survivorship, lineage, review queue and idempotency tests."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import src.publish as publish
from src.duplicate_detection import find_duplicates
from src.ingestion import ingest
from src.pipeline import run_pipeline
from src.survivorship import build_masters
from src.validation import validate_records
from tests.helpers import tmpdir, write_csv


def _detect(rows):
    with tmpdir() as d:
        valid, _ = validate_records(ingest(write_csv(d, rows)))
    clusters, review = find_duplicates(valid)
    return clusters, review, build_masters(clusters)


def test_exact_duplicates_are_merged():
    _, _, masters = _detect([["C001", "John Smith", "john@gmail.com", "9876543210"],
                             ["C002", "John Smith", "john@gmail.com", "9876543210"]])
    assert len(masters) == 1 and masters[0]["source_ids"] == ["C001", "C002"]


def test_john_smith_vs_jon_smith_found():
    _, _, masters = _detect([["C001", "John Smith", "john@gmail.com", "9876543210"],
                             ["C002", "Jon Smith", "other@gmail.com", "9876543210"]])
    assert len(masters) == 1  # similar name + same phone -> auto merge


def test_jon_smith_without_identifier_goes_to_review():
    _, review, masters = _detect([["C001", "John Smith", "a@gmail.com", "9876543210"],
                                  ["C002", "Jon Smith", "b@gmail.com", "9123456780"]])
    assert len(masters) == 2 and len(review) == 1
    assert {review.iloc[0]["record1"], review.iloc[0]["record2"]} == {"C001", "C002"}


def test_john_smyth_not_auto_merged_goes_to_review():
    _, review, masters = _detect([["C001", "John Smith", "a@gmail.com", "9876543210"],
                                  ["C002", "John Smyth", "b@gmail.com", "9123456780"]])
    assert len(masters) == 2 and len(review) == 1


def test_different_people_not_matched():
    _, review, masters = _detect([["C001", "John Smith", "a@gmail.com", "9876543210"],
                                  ["C002", "Alice Johnson", "b@gmail.com", "9123456780"]])
    assert len(masters) == 2 and review.empty


def test_survivorship_chooses_non_null_value():
    _, _, masters = _detect([["C001", "John Smith", "john@gmail.com", ""],
                             ["C002", "John Smith", "john@gmail.com", "9876543210"]])
    assert masters[0]["phone"] == "9876543210" and masters[0]["email"] == "john@gmail.com"


def test_lineage_tracks_sources():
    with tmpdir() as d:
        path = write_csv(d, [["C001", "John Smith", "john@gmail.com", "9876543210"],
                             ["C002", "Jon Smith", "john@gmail.com", "9876543210"],
                             ["C004", "Alice Johnson", "alice@gmail.com", "9999999999"]])
        run_pipeline(path, f"{d}/out", f"{d}/logs")
        lineage = json.loads(Path(d, "out", "lineage.json").read_text())
        assert lineage[0]["master_id"] == "M00001"
        assert lineage[0]["source_records"] == ["C001", "C002"]
        assert lineage[1]["source_records"] == ["C004"]


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_pipeline_is_idempotent():
    sample = Path("data/sample/customers.csv")
    data_files = ["merged_records.csv", "review_queue.csv", "rejected_records.csv", "lineage.json"]
    with tmpdir() as d:
        out = Path(d, "out")
        run_pipeline(sample, out, f"{d}/logs")
        first = {f: _digest(out / f) for f in data_files}
        run_pipeline(sample, out, f"{d}/logs")
        second = {f: _digest(out / f) for f in data_files}
        assert first == second
        assert len(pd.read_csv(out / "run_metrics.csv")) == 1  # metrics row replaced, not appended


def test_pipeline_recovers_after_partial_publish_failure(tmp_path, monkeypatch):
    sample = Path("data/sample/customers.csv")
    out = tmp_path / "out"
    original_write_csv = publish._write_csv
    calls = 0

    def fail_on_second_csv_write(df, path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated publish failure")
        original_write_csv(df, path)

    monkeypatch.setattr(publish, "_write_csv", fail_on_second_csv_write)
    with pytest.raises(OSError, match="simulated publish failure"):
        run_pipeline(sample, out, tmp_path / "logs")

    monkeypatch.setattr(publish, "_write_csv", original_write_csv)
    summary = run_pipeline(sample, out, tmp_path / "logs")

    assert summary["status"] == "SUCCESS"
    assert len(pd.read_csv(out / "merged_records.csv")) == 10
    assert len(pd.read_csv(out / "review_queue.csv")) == 3
    assert len(pd.read_csv(out / "rejected_records.csv")) == 3
    assert len(json.loads((out / "lineage.json").read_text())) == 10
    assert len(pd.read_csv(out / "run_metrics.csv")) == 1


def test_sample_dataset_expected_counts():
    with tmpdir() as d:
        s = run_pipeline("data/sample/customers.csv", f"{d}/out", f"{d}/logs")
    assert (s["input_count"], s["valid_count"], s["reject_count"]) == (16, 13, 3)
    assert (s["output_count"], s["duplicates_removed"], s["review_pairs"]) == (10, 3, 3)
