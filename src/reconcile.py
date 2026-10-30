"""Stage 7 - Reconciliation: prove source-to-target counts and keys add up."""
import pandas as pd

CHECK_COLUMNS = ["check_name", "expected", "actual", "status", "detail"]


def _check(name: str, expected, actual, detail: str = "") -> dict:
    return {"check_name": name, "expected": expected, "actual": actual,
            "status": "PASS" if expected == actual else "FAIL", "detail": detail}


def reconcile(input_count: int, valid: pd.DataFrame, rejected: pd.DataFrame,
              masters: list[dict], review_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per reconciliation check."""
    valid_ids = list(valid["customer_id"])
    master_sources = [cid for m in masters for cid in m["source_ids"]]
    master_ids = [m["master_id"] for m in masters]
    owner = {cid: m["master_id"] for m in masters for cid in m["source_ids"]}

    review_same_master = 0
    review_unknown_id = 0
    for r1, r2 in zip(review_df["record1"], review_df["record2"]):
        if r1 not in owner or r2 not in owner:
            review_unknown_id += 1
        elif owner[r1] == owner[r2]:
            review_same_master += 1

    checks = [
        _check("input_equals_valid_plus_rejected", input_count, len(valid) + len(rejected),
               "every input row is either valid or rejected"),
        _check("valid_equals_sum_of_master_source_counts", len(valid), len(master_sources),
               "no valid record lost or duplicated by merging"),
        _check("every_valid_id_in_exactly_one_master", sorted(valid_ids), sorted(master_sources),
               "lineage covers all valid ids exactly once"),
        _check("master_ids_unique", len(master_ids), len(set(master_ids))),
        _check("rejects_have_reason", 0, int((rejected["reason"].fillna("") == "").sum()),
               "every rejected row is explained"),
        _check("review_pairs_reference_known_ids", 0, review_unknown_id),
        _check("review_pairs_not_already_merged", 0, review_same_master),
    ]
    out = pd.DataFrame(checks, columns=CHECK_COLUMNS)
    # keep list-valued comparisons readable in the CSV
    for col in ("expected", "actual"):
        out[col] = out[col].map(lambda v: f"{len(v)} ids" if isinstance(v, list) else v)
    return out
