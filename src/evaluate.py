"""Compare pipeline output against the generator's ground-truth labels.

    python -m src.evaluate --labels data/generated/customers_1000_labels.csv --outputs outputs

Pairwise metrics over records that passed validation:
  precision = merged pairs that are truly the same entity / all merged pairs
  recall    = truly-same pairs that were merged / all truly-same pairs
  review_catch = of the true pairs that were NOT merged, how many sit in the review queue
Also checks that every labelled-invalid row was rejected.
"""
import argparse
import json
from itertools import combinations
from pathlib import Path

import pandas as pd


def evaluate(labels_path, outputs_dir) -> dict:
    out = Path(outputs_dir)
    labels = pd.read_csv(labels_path, dtype=str, keep_default_na=False)
    merged = pd.read_csv(out / "merged_records.csv", dtype=str, keep_default_na=False)
    review = pd.read_csv(out / "review_queue.csv", dtype=str, keep_default_na=False)
    rejected = pd.read_csv(out / "rejected_records.csv", dtype=str, keep_default_na=False)

    owner = {}  # customer_id -> master_id
    for mid, sources in zip(merged["master_id"], merged["source_ids"]):
        for cid in sources.split("|"):
            owner[cid] = mid

    entity = dict(zip(labels["customer_id"], labels["true_entity_id"]))
    valid_ids = set(owner)

    by_entity: dict[str, list[str]] = {}
    for cid in valid_ids:
        by_entity.setdefault(entity[cid], []).append(cid)
    true_pairs = {frozenset(p) for ids in by_entity.values() for p in combinations(sorted(ids), 2)}

    by_master: dict[str, list[str]] = {}
    for cid, mid in owner.items():
        by_master.setdefault(mid, []).append(cid)
    pred_pairs = {frozenset(p) for ids in by_master.values() for p in combinations(sorted(ids), 2)}

    hit = true_pairs & pred_pairs
    missed = true_pairs - pred_pairs
    review_cluster_pairs = {frozenset((owner[a], owner[b])) for a, b in zip(review["record1"], review["record2"])
                            if a in owner and b in owner}
    missed_in_review = sum(1 for p in missed if frozenset(owner[c] for c in p) in review_cluster_pairs)

    invalid_ids = set(labels.loc[labels["record_type"] == "invalid", "customer_id"])
    rejected_ids = set(rejected["record_id"])

    return {
        "true_duplicate_pairs": len(true_pairs),
        "predicted_merged_pairs": len(pred_pairs),
        "precision": round(len(hit) / len(pred_pairs), 4) if pred_pairs else 1.0,
        "recall": round(len(hit) / len(true_pairs), 4) if true_pairs else 1.0,
        "missed_pairs": len(missed),
        "missed_pairs_found_in_review_queue": missed_in_review,
        "labelled_invalid_rows": len(invalid_ids),
        "invalid_rows_rejected": len(invalid_ids & rejected_ids),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--outputs", default="outputs")
    args = ap.parse_args()
    report = evaluate(args.labels, args.outputs)
    print(json.dumps(report, indent=2))
    (Path(args.outputs) / "evaluation_report.json").write_text(json.dumps(report, indent=2) + "\n")
