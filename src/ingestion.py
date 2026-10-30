"""Stage 1 - Ingestion: read the CSV and check the schema."""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("dedup_pipeline")

REQUIRED_COLUMNS = ["customer_id", "name", "email", "phone"]
OPTIONAL_COLUMNS = ["address"]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
OUTPUT_COLUMNS = ALL_COLUMNS + ["source_row"]   # source_row = line number in the input file


class IngestionError(Exception):
    """The input file could not be read."""


class SchemaError(IngestionError):
    """The input file is missing required columns -> whole file is rejected."""


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in OUTPUT_COLUMNS})


def ingest(path: str | Path) -> pd.DataFrame:
    """Read the CSV as strings (so phone numbers keep leading digits intact).

    * 0-byte file or header-only file -> empty DataFrame (0 records), not a crash.
    * Missing required column         -> SchemaError (file rejected).
    """
    path = Path(path)
    if not path.exists():
        raise IngestionError(f"input file not found: {path}")

    if path.stat().st_size == 0:
        log.warning("input file is empty (0 bytes): %s", path)
        return _empty_frame()

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        log.warning("input file has no rows: %s", path)
        return _empty_frame()

    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"missing required column(s): {', '.join(missing)}")

    extra = [c for c in df.columns if c not in ALL_COLUMNS]
    if extra:  # unexpected schema change: tolerated, but visible in the log
        log.warning("unexpected extra column(s) ignored: %s", ", ".join(extra))

    if "address" not in df.columns:
        df["address"] = ""
    df["source_row"] = [str(n) for n in range(2, len(df) + 2)]  # line 1 is the header
    return df[OUTPUT_COLUMNS].copy()
