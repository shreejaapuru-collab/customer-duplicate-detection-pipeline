"""Generator is reproducible, keeps labels separate from input, and the pipeline scores well against them."""
import subprocess
import sys
from pathlib import Path

from src.evaluate import evaluate
from src.pipeline import run_pipeline
from tests.helpers import tmpdir


def _generate(path, rows=400, seed=1):
    subprocess.run([sys.executable, "generator.py", "--rows", str(rows), "--seed", str(seed),
                    "--out", str(path)], check=True, capture_output=True)


def test_generator_is_reproducible_and_labels_are_separate():
    with tmpdir() as d:
        a, b = Path(d, "a.csv"), Path(d, "b.csv")
        _generate(a)
        _generate(b)
        assert a.read_bytes() == b.read_bytes()
        assert Path(d, "a_labels.csv").read_bytes() == Path(d, "b_labels.csv").read_bytes()
        header = a.read_text().splitlines()[0]
        assert header == "customer_id,name,email,phone,address"       # no label columns in the input
        assert "true_entity_id" in Path(d, "a_labels.csv").read_text().splitlines()[0]


def test_pipeline_quality_against_ground_truth():
    with tmpdir() as d:
        data = Path(d, "c.csv")
        _generate(data, rows=600, seed=5)
        run_pipeline(data, f"{d}/out", f"{d}/logs")
        report = evaluate(Path(d, "c_labels.csv"), f"{d}/out")
        assert report["precision"] >= 0.95
        assert report["recall"] >= 0.80
        assert report["invalid_rows_rejected"] == report["labelled_invalid_rows"]
