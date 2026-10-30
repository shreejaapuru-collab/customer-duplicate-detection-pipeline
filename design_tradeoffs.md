# Design and Trade-off Note

This project is designed to find likely duplicate customers without hiding why a match was made. It favors
clear rules, traceable outputs, and safe reruns over adding services or model-training complexity.

## Key decisions

| Decision | Why it fits this project | What it costs |
|---|---|---|
| Rule-based scoring with RapidFuzz and shared identifiers | Each merge has a reason that can be inspected; no training data is needed. | It is less adaptable than a model trained on reviewed matches. |
| A high bar for automatic merges | A wrong merge can damage customer data, so uncertain cases stay separate. | Some real duplicates need a human to approve them. |
| A review queue for ambiguous pairs | Reviewers get the cases where the available evidence is not strong enough. | Someone has to work through the queue; similar suggestions are grouped to keep it manageable. |
| Transitive clusters using union-find | Pairwise matches can be turned into one master record per person. | A mistaken link can join an entire cluster. |
| Email required; phone optional | A missing phone can be filled from another record in the same cluster. | Records without an email are rejected, even when their phone is present. |
| Stable ordering and content-based run IDs | Re-running the same data produces repeatable IDs and replaces the same metrics row. | Adding records can change the numbered master IDs. |
| Atomic file writes, metrics written last | A run can be retried, and the metrics help show whether it completed. | The output files are not replaced together as one transaction. |

## Choosing values for a merged record
Ignore nulls -> most frequent value -> value from the most complete record -> lowest `customer_id`.
Fields where sources disagreed are listed in `conflicting_fields` so nothing is silently overwritten.

## Performance and scope

Comparing every possible pair grows as O(n²), which quickly becomes expensive. The pipeline first groups
records into blocks using phone, email, and name keys, then scores only pairs within the same block.

One optimization tested for name-only review suggestions was tightening the name block from the first and
last initials to the first two letters of each name, using `name_block_prefix`.

Auto-merges and identifier-based review pairs are found through the email/phone blocks, so the name block only
feeds *name-only* review suggestions. Tightening it cannot cause a wrong merge.
Measured on 10,000 synthetic rows (pure-Python matcher, seed 42):

| name_block_prefix | pairs compared | detect time | precision | recall |
|---|---|---|---|---|
| 1 (loose) | 292,312 | 22.5 s | 1.00 | 0.937 |
| 2 (tight, default) | 91,050 | 6.9 s | 1.00 | 0.937 |

In this benchmark, the tighter block made about three times fewer comparisons and took about a third of the
detection time, with the same precision and recall. The trade-off was fewer name-only suggestions in the
review queue. A separate 30,000-row run with `name_block_prefix=2` compared 760,639 pairs rather than
450 million possible pairs, with 1.00 precision and 0.949 recall. These benchmark timings used the slower
pure-Python fallback matcher and may differ on other machines.

The intended and measured target for this project is 10,000 input rows. The 30,000-row run is included as a
scaling observation, not a promise of production capacity. Performance at 100,000 rows has not been measured.

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
