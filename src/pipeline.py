"""Orchestrates all stages: ingest -> validate -> detect -> survive -> lineage -> publish."""
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from .duplicate_detection import MatchConfig, find_duplicates
from .ingestion import IngestionError, ingest
from .lineage import build_lineage
from .logger import close_logger, get_logger
from .publish import METRIC_COLUMNS, publish_outputs, upsert_metrics
from .similarity import BACKEND
from .survivorship import build_masters
from .validation import validate_records


def compute_run_id(input_path, cfg: MatchConfig) -> str:
    """Deterministic: same input content + same config => same run_id (idempotent metrics)."""
    h = hashlib.sha256()
    p = Path(input_path)
    h.update(p.read_bytes() if p.exists() else str(p).encode())
    h.update(repr(cfg).encode())
    return "run_" + h.hexdigest()[:10]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_pipeline(input_path, output_dir="outputs", log_dir="logs", cfg: MatchConfig | None = None) -> dict:
    cfg = cfg or MatchConfig()
    log: logging.Logger = get_logger(log_dir)
    try:
        start = _now()
        run_id = compute_run_id(input_path, cfg)
        log.info("run_id=%s input=%s matcher=%s", run_id, input_path, BACKEND)

        try:
            raw = ingest(input_path)
        except IngestionError as exc:
            log.error("FILE REJECTED: %s", exc)
            row = dict.fromkeys(METRIC_COLUMNS, 0)
            row.update(run_id=run_id, start_time=start, end_time=_now(), status="FILE_REJECTED")
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            upsert_metrics(Path(output_dir) / "run_metrics.csv", row)
            raise

        valid, rejected = validate_records(raw)
        clusters, review_df = find_duplicates(valid, cfg)
        masters = build_masters(clusters)
        lineage = build_lineage(masters, run_id)

        summary = {
            "run_id": run_id, "start_time": start, "end_time": "", "status": "SUCCESS",
            "input_count": len(raw), "valid_count": len(valid), "reject_count": len(rejected),
            "duplicates_removed": len(valid) - len(masters),
            "merged_masters": sum(1 for m in masters if len(m["source_ids"]) > 1),
            "output_count": len(masters), "review_pairs": len(review_df),
        }
        summary["end_time"] = _now()
        publish_outputs(output_dir, masters, review_df, rejected, lineage, summary)

        log.info("run_id=%s", run_id)
        log.info("input_rows=%d", summary["input_count"])
        log.info("valid_rows=%d", summary["valid_count"])
        log.info("rejected_rows=%d", summary["reject_count"])
        log.info("duplicates=%d", summary["duplicates_removed"])
        log.info("merged_records=%d", summary["merged_masters"])
        log.info("output_records=%d", summary["output_count"])
        log.info("review_pairs=%d", summary["review_pairs"])
        log.info("outputs written to %s/", output_dir)
        return summary
    finally:
        close_logger(log)
