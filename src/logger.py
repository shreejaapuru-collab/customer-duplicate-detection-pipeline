"""Logging setup: console + logs/pipeline.log."""
import logging
import sys
from pathlib import Path

LOGGER_NAME = "dedup_pipeline"


def get_logger(log_dir: str | None = "logs") -> logging.Logger:
    """Return the pipeline logger. Safe to call repeatedly (handlers are reset)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(Path(log_dir) / "pipeline.log", encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    return logger


def close_logger(logger: logging.Logger) -> None:
    """Close and remove handlers so log files can be released on Windows."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
