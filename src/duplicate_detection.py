"""Stage 3 - Duplicate detection.

Pair decision rules (see docs/architecture.md):

  1. same email AND same phone                          -> MERGE   (exact)
  2. name similarity >= 90 AND same email or phone      -> MERGE   (fuzzy + identifier)
  3. name similarity >= 75 AND same email or phone      -> REVIEW
     name similarity >= 88 with no shared identifier    -> REVIEW
  4. anything else                                      -> not a match

Only MERGE pairs are joined into clusters. REVIEW pairs are never auto-merged;
they are written to review_queue.csv for a human.

Scalability: instead of comparing every pair (O(n^2)) we only compare records
that share a "block": same phone, same email, or same (first-initial, last-initial).
"""
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .similarity import name_similarity


@dataclass(frozen=True)
class MatchConfig:
    auto_merge_threshold: float = 90.0
    review_threshold_with_identifier: float = 75.0
    review_threshold_name_only: float = 88.0
    name_block_prefix: int = 2   # letters of first and last name used in the name-block key


REVIEW_COLUMNS = [
    "record1", "record2", "similarity_score", "reason",
    "name_1", "name_2", "email_1", "email_2", "phone_1", "phone_2",
]


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:  # smaller index becomes root -> deterministic clusters
            self.parent[max(ra, rb)] = min(ra, rb)


def score_pair(r1: dict, r2: dict, cfg: MatchConfig = MatchConfig()):
    """Return (decision, name_similarity, reason); decision is 'merge', 'review' or None."""
    email_eq = r1["email"] == r2["email"]
    phone_eq = bool(r1["phone"]) and r1["phone"] == r2["phone"]
    sim = round(name_similarity(r1["name_key"], r2["name_key"]), 1)

    if email_eq and phone_eq:
        return "merge", sim, "exact_email_and_phone"

    if email_eq or phone_eq:
        shared = "email" if email_eq else "phone"
        if sim >= cfg.auto_merge_threshold:
            return "merge", sim, f"similar_name_same_{shared}"
        if sim >= cfg.review_threshold_with_identifier:
            return "review", sim, f"name_below_auto_threshold_same_{shared}"
        return None, sim, ""

    if sim >= cfg.review_threshold_name_only:
        return "review", sim, "similar_name_no_shared_identifier"
    return None, sim, ""


def _block_key(name_key: str, prefix: int = 2) -> tuple[str, str]:
    """(first `prefix` letters of first name, first `prefix` letters of last name).

    prefix=1 -> loose blocks: more comparisons, catches typos near the start of a name
    prefix=2 -> tight blocks: far fewer comparisons (the optimisation, see docs/design_tradeoffs.md)

    NOTE: auto-merges and identifier-based review pairs are found through the email/phone
    blocks, so this key only affects name-only review pairs - it can never cause a wrong merge.
    """
    tokens = name_key.split()
    return (tokens[0][:prefix], tokens[-1][:prefix]) if tokens else ("", "")


def build_blocks(recs: list[dict], cfg: MatchConfig = MatchConfig()) -> dict:
    blocks: dict[tuple, list[int]] = defaultdict(list)
    for i, r in enumerate(recs):
        blocks[("name",) + _block_key(r["name_key"], cfg.name_block_prefix)].append(i)
        blocks[("email", r["email"])].append(i)
        if r["phone"]:
            blocks[("phone", r["phone"])].append(i)
    return blocks


def find_duplicates(valid: pd.DataFrame, cfg: MatchConfig = MatchConfig(), stats: dict | None = None):
    """Return (clusters, review_df).

    clusters: list of {"records": [dict, ...], "reasons": [str, ...]}, ordered by
              smallest customer_id; singletons are included (cluster of one).
    review_df: pairs a human must look at (one best pair per pair of clusters).
    """
    recs = valid.sort_values("customer_id", kind="stable").to_dict("records")
    uf = _UnionFind(len(recs))

    blocks = build_blocks(recs, cfg)

    compared = 0
    merge_pairs, review_pairs = [], []
    for members in blocks.values():
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]  # i < j (members are in ascending order)
                compared += 1  # a pair sharing 2 blocks is scored twice - harmless, results are identical
                decision, sim, reason = score_pair(recs[i], recs[j], cfg)
                if decision == "merge":
                    uf.union(i, j)
                    merge_pairs.append((i, reason))
                elif decision == "review":
                    review_pairs.append((i, j, sim, reason))
    if stats is not None:
        stats["pairs_compared"] = compared

    # build clusters
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(recs)):
        groups[uf.find(i)].append(i)
    reasons_by_root: dict[int, set[str]] = defaultdict(set)
    for i, reason in merge_pairs:
        reasons_by_root[uf.find(i)].add(reason)
    clusters = [
        {"records": [recs[i] for i in idxs], "reasons": sorted(reasons_by_root.get(root, set()))}
        for root, idxs in sorted(groups.items())
    ]

    # review queue: drop pairs already merged together; keep best pair per cluster-pair
    best: dict[tuple[int, int], tuple] = {}
    for i, j, sim, reason in review_pairs:
        key = tuple(sorted((uf.find(i), uf.find(j))))
        if key[0] == key[1]:
            continue
        if key not in best or (sim, -i, -j) > (best[key][2], -best[key][0], -best[key][1]):
            best[key] = (i, j, sim, reason)

    rows = []
    for i, j, sim, reason in best.values():
        a, b = recs[i], recs[j]
        rows.append({
            "record1": a["customer_id"], "record2": b["customer_id"],
            "similarity_score": sim, "reason": reason,
            "name_1": a["name"], "name_2": b["name"],
            "email_1": a["email"], "email_2": b["email"],
            "phone_1": a["phone"], "phone_2": b["phone"],
        })
    review_df = pd.DataFrame(rows, columns=REVIEW_COLUMNS)
    if not review_df.empty:
        review_df = review_df.sort_values(
            ["similarity_score", "record1", "record2"], ascending=[False, True, True], kind="stable"
        ).reset_index(drop=True)
    return clusters, review_df
