"""Stage 4 - Survivorship: collapse each duplicate cluster into one golden record.

Rule per field (name, email, phone, address):
  1. ignore null values                      ("choose non-null")
  2. if several different values remain, pick the most frequent one
  3. tie -> take it from the most complete record, then the lowest customer_id
"""
from collections import Counter

FIELDS = ["name", "email", "phone", "address"]
RULE_DESCRIPTION = "non_null > most_frequent > most_complete_record > lowest_customer_id"


def _is_null(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or v == ""


def _completeness(rec: dict) -> int:
    return sum(0 if _is_null(rec.get(f)) else 1 for f in FIELDS)


def merge_cluster(records: list[dict]) -> tuple[dict, list[str]]:
    """Return (golden_values, conflicting_fields)."""
    ordered = sorted(records, key=lambda r: (-_completeness(r), r["customer_id"]))
    merged, conflicts = {}, []
    for field in FIELDS:
        values = [r[field] for r in ordered if not _is_null(r.get(field))]
        if not values:
            merged[field] = None
            continue
        counts = Counter(values)
        if len(counts) > 1:
            conflicts.append(field)
        top = max(counts.values())
        merged[field] = next(v for v in values if counts[v] == top)  # first in priority order
    return merged, conflicts


def build_masters(clusters: list[dict]) -> list[dict]:
    """One master record per cluster, with a deterministic master_id (M00001, ...)."""
    masters = []
    for n, cluster in enumerate(clusters, start=1):
        records = cluster["records"]
        values, conflicts = merge_cluster(records)
        masters.append({
            "master_id": f"M{n:05d}",
            **values,
            "source_ids": [r["customer_id"] for r in records],
            "match_reasons": cluster["reasons"],
            "conflicting_fields": conflicts,
        })
    return masters
