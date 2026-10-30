"""Stage 5 - Lineage: record which source records produced each master record."""


def build_lineage(masters: list[dict], run_id: str) -> list[dict]:
    return [
        {
            "master_id": m["master_id"],
            "source_records": m["source_ids"],
            "match_reasons": m["match_reasons"],
            "conflicting_fields": m["conflicting_fields"],
            "survivorship_rule": "non_null > most_frequent > most_complete_record > lowest_customer_id",
            "run_id": run_id,
        }
        for m in masters
    ]
