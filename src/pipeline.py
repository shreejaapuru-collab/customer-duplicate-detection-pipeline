"""Orchestrates all stages: ingest -> validate -> detect -> survive -> lineage -> reconcile -> publish."""
import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .duplicate_detection import MatchConfig, find_duplicates
from .ingestion import IngestionError, ingest
from .lineage import build_lineage
from .logger import close_logger, get_logger
from .publish import METRIC_COLUMNS, publish_outputs, upsert_metrics
from .reconcile import reconcile
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


def _record_failure(output_dir, run_id, source_file, start, status, reason, timings) -> None:
    row = dict.fromkeys(METRIC_COLUMNS, 0)
    row.update(run_id=run_id, source_file=source_file, start_time=start, end_time=_now(),
               status=status, failure_reason=reason, **timings)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    upsert_metrics(Path(output_dir) / "run_metrics.csv", row)


def run_pipeline(input_path, output_dir="outputs", log_dir="logs", cfg: MatchConfig | None = None) -> dict:
    logger = logging.getLogger("dedup_pipeline")
    try:
        return _run_pipeline(input_path, output_dir, log_dir, cfg)
    finally:
        close_logger(logger)


def _run_pipeline(input_path, output_dir="outputs", log_dir="logs", cfg: MatchConfig | None = None) -> dict:
    cfg = cfg or MatchConfig()
    log: logging.Logger = get_logger(log_dir)
    start, t0 = _now(), time.perf_counter()
    run_id = compute_run_id(input_path, cfg)
    source_file = Path(input_path).name
    timings: dict[str, float] = {}
    log.info("run_id=%s input=%s matcher=%s", run_id, input_path, BACKEND)

    def lap(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round(now - since, 3)
        return now

    try:
        t = time.perf_counter()
        raw = ingest(input_path)
        t = lap("ingest_s", t)

        valid, rejected = validate_records(raw)
        t = lap("validate_s", t)

        stats: dict = {}
        clusters, review_df = find_duplicates(valid, cfg, stats)
        t = lap("detect_s", t)

        masters = build_masters(clusters)
        lineage = build_lineage(masters, run_id)
        recon = reconcile(len(raw), valid, rejected, masters, review_df)
        recon_failures = int((recon["status"] == "FAIL").sum())
        t = lap("merge_s", t)

        summary = {
            "run_id": run_id, "source_file": source_file, "start_time": start, "end_time": "",
            "status": "SUCCESS" if recon_failures == 0 else "RECONCILIATION_FAILED",
            "failure_reason": "" if recon_failures == 0 else f"{recon_failures} reconciliation check(s) failed",
            "input_count": len(raw), "valid_count": len(valid), "reject_count": len(rejected),
            "duplicates_removed": len(valid) - len(masters),
            "merged_masters": sum(1 for m in masters if len(m["source_ids"]) > 1),
            "output_count": len(masters), "review_pairs": len(review_df),
            "pairs_compared": stats.get("pairs_compared", 0),
            "reconciliation_failures": recon_failures,
        }
        summary["end_time"] = _now()
        summary.update(timings)
        summary["publish_s"] = 0.0
        summary["total_s"] = 0.0
        # publish, then record the real publish/total time in the metrics row
        t_pub = time.perf_counter()
        publish_outputs(output_dir, masters, review_df, rejected, lineage, recon,
                        summary, run_id, source_file)
        summary["publish_s"] = round(time.perf_counter() - t_pub, 3)
        summary["total_s"] = round(time.perf_counter() - t0, 3)
        upsert_metrics(Path(output_dir) / "run_metrics.csv", summary)

    except IngestionError as exc:  # bad file: reject the whole file, keep old outputs untouched
        log.error("FILE REJECTED: %s", exc)
        _record_failure(output_dir, run_id, source_file, start, "FILE_REJECTED", str(exc), timings)
        raise
    except Exception as exc:  # partial failure: record why, keep old outputs, let the operator retry
        log.exception("RUN FAILED: %s", exc)
        _record_failure(output_dir, run_id, source_file, start, "FAILED", f"{type(exc).__name__}: {exc}", timings)
        raise

    log.info("run_id=%s", run_id)
    log.info("input_rows=%d", summary["input_count"])
    log.info("valid_rows=%d", summary["valid_count"])
    log.info("rejected_rows=%d", summary["reject_count"])
    log.info("duplicates=%d", summary["duplicates_removed"])
    log.info("merged_records=%d", summary["merged_masters"])
    log.info("output_records=%d", summary["output_count"])
    log.info("review_pairs=%d", summary["review_pairs"])
    log.info("pairs_compared=%d", summary["pairs_compared"])
    log.info("reconciliation: %d failure(s)", recon_failures)
    log.info("timings: %s total_s=%s", timings, summary["total_s"])
    log.info("outputs written to %s/", output_dir)
    return summary
