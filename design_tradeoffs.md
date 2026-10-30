# Design and Trade-off Note

## Goal
Find exact and probable duplicate customers, merge them with transparent rules, keep lineage, and send
uncertain cases to a human. Priorities (from the brief): correctness, clarity, testing, safe reruns.

## Key decisions

| Decision | Why | Trade-off |
|---|---|---|
| Rule-based scoring (RapidFuzz ratio + shared email/phone), no ML | Explainable: every merge has a recorded reason; no training data needed | Less flexible than a learned model |
| Auto-merge only with a strong signal (name >= 90 **and** shared email/phone, or exact email+phone) | A wrong merge corrupts customer data; a missed merge is cheap to fix | Some true duplicates land in the review queue instead of being merged |
| Review queue for uncertain pairs | Humans decide ambiguous cases (John Smith / John Smyth) | Needs a person; queue is de-duplicated to one best pair per pair of clusters |
| Transitive clustering (union-find) | A~B and B~C means one person | One bad link can over-merge; review pairs never join clusters |
| Phone is optional, email required | A null phone is exactly what survivorship should fill from a duplicate | A record with no email is rejected even if the phone is good |
| Deterministic everything (sorted input, `M00001` ids, content-hash `run_id`) | Reruns and row-order changes give identical outputs | master_id values can shift if new records change the sort order |
| Atomic writes, metrics written last | A crash never leaves a half-written file; a missing/FAILED metrics row flags an incomplete run | Files are not swapped as one transaction (see restart section in README) |

## Survivorship (per field)
Ignore nulls -> most frequent value -> value from the most complete record -> lowest `customer_id`.
Fields where sources disagreed are listed in `conflicting_fields` so nothing is silently overwritten.

## Performance reasoning
Comparing every pair of n records is O(n^2): 100,000 rows = ~5 billion comparisons.
1. **Blocking (baseline):** only compare records that share a phone, an email, or a name block.
2. **Optimisation:** tighten the name block from (first letter, last letter) to
   (first 2 letters of first name, first 2 letters of last name) via `name_block_prefix`.

Auto-merges and identifier-based review pairs are found through the email/phone blocks, so the name block only
feeds *name-only* review suggestions. Tightening it cannot cause a wrong merge.
Measured on 10,000 synthetic rows (pure-Python matcher, seed 42):

| name_block_prefix | pairs compared | detect time | precision | recall |
|---|---|---|---|---|
| 1 (loose) | 292,312 | 22.5 s | 1.00 | 0.937 |
| 2 (tight, default) | 91,050 | 6.9 s | 1.00 | 0.937 |

About 3x fewer comparisons and 3x faster, with the same precision and recall; the only cost is that fewer
name-only pairs are suggested for review (111 of 141 missed pairs still appear in the review queue, vs 140).
Scaling check (same settings, `name_block_prefix=2`): 30,000 rows -> 760,639 pairs compared (0.17% of the
450 million all-pairs comparisons), 72 s detect time, precision 1.00, recall 0.949.
These numbers use the slow pure-Python fallback matcher; RapidFuzz is much faster.

The intended and measured operating target for this project is 10,000 input rows. The larger
30,000-row run above is a scaling observation, not a required or guaranteed operating target;
100,000-row performance has not been measured.

## Quality measurement
`generator.py` writes expected-answer labels to a separate `*_labels.csv`. `src/evaluate.py` compares pipeline
output with those labels (pairwise precision/recall). `reconciliation_report.csv` proves counts add up on
every run (input = valid + rejected; every valid id is in exactly one master; no review pair is already merged).

## Known limitations
* Matching uses name, email and phone only (address is carried through, not matched).
* Two different people with identical names and no shared identifier go to review by design.
* A typo in the first two letters of a first or last name with nothing shared will not be suggested for review.
* All data is held in memory; beyond a few million rows use Spark/Dask or database-side blocking joins.
* Late-arriving updates are not modelled: the input is a full snapshot, so each run recomputes from scratch.
* Referential integrity / invalid reference keys do not apply: there is a single customer table.
