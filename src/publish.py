"""Stage 6 - Publish outputs. Files are overwritten atomically, so reruns never duplicate rows.

Order matters for recovery: data files first, run_metrics.csv LAST. If a run dies half-way,
the metrics row is missing/FAILED, which tells the operator the outputs are not trustworthy
until the run is repeated (a rerun is safe - it overwrites everything deterministically).
"""
import json
import os
from pathlib import Path

import pandas as pd

MASTER_COLUMNS = ["master_id", "name", "email", "phone", "address", "source_ids", "source_count",
                  "match_reasons", "conflicting_fields", "run_id", "source_file"]
REJECT_OUT_COLUMNS = ["record_id", "reason", "source_file", "source_row", "run_id",
                      "raw_name", "raw_email", "raw_phone"]
METRIC_COLUMNS = ["run_id", "source_file", "start_time", "end_time", "status", "failure_reason",
                  "input_count", "valid_count", "reject_count", "duplicates_removed", "merged_masters",
                  "output_count", "review_pairs", "pairs_compared", "reconciliation_failures",
                  "ingest_s", "validate_s", "detect_s", "merge_s", "publish_s", "total_s"]


def _atomic_write(path: Path, writer) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    writer(tmp)
    os.replace(tmp, path)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    _atomic_write(path, lambda p: df.to_csv(p, index=False, lineterminator="\n", encoding="utf-8"))


def masters_to_frame(masters: list[dict], run_id: str = "", source_file: str = "") -> pd.DataFrame:
    rows = [{
        "master_id": m["master_id"], "name": m["name"], "email": m["email"],
        "phone": m["phone"], "address": m["address"],
        "source_ids": "|".join(m["source_ids"]), "source_count": len(m["source_ids"]),
        "match_reasons": "|".join(m["match_reasons"]),
        "conflicting_fields": "|".join(m["conflicting_fields"]),
        "run_id": run_id, "source_file": source_file,
    } for m in masters]
    return pd.DataFrame(rows, columns=MASTER_COLUMNS)


def upsert_metrics(path: Path, row: dict) -> None:
    """Replace the row with the same run_id (same input => same run_id), else append."""
    new = pd.DataFrame([row]).reindex(columns=METRIC_COLUMNS).astype(object)
    if path.exists() and path.stat().st_size > 0:
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        old = old[old["run_id"] != row["run_id"]]
        new = pd.concat([old, new.astype(str)], ignore_index=True)
    _write_csv(new.reindex(columns=METRIC_COLUMNS), path)


def publish_outputs(output_dir, masters, review_df, rejected_df, lineage, recon_df,
                    metrics_row, run_id="", source_file="") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rejected_out = rejected_df.copy()
    rejected_out["source_file"] = source_file
    rejected_out["run_id"] = run_id

    _write_csv(masters_to_frame(masters, run_id, source_file), out / "merged_records.csv")
    _write_csv(review_df, out / "review_queue.csv")
    _write_csv(rejected_out.reindex(columns=REJECT_OUT_COLUMNS), out / "rejected_records.csv")
    _write_csv(recon_df, out / "reconciliation_report.csv")
    _atomic_write(out / "lineage.json",
                  lambda p: Path(p).write_text(json.dumps(lineage, indent=2) + "\n", encoding="utf-8"))
    upsert_metrics(out / "run_metrics.csv", metrics_row)   # LAST: marks the run as complete
