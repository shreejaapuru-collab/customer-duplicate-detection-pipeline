# Data Dictionary

This page describes the columns used by the customer pipeline and the files it writes. Input values are
read as strings so identifiers and phone numbers keep their original formatting until validation.

## Input - `customers.csv`
| Column | Required | Description |
|---|---|---|
| customer_id | yes | Unique source record id |
| name | yes | Full name |
| email | yes | Valid email (stored lower-case) |
| phone | no | 10-digit number starting 6-9; `+91`/`0` prefix stripped; null allowed |
| address | no | Free text; carried into the merged record |

When it creates synthetic data, the generator also writes a separate `customers_<n>_labels.csv` file.
That file contains `customer_id`, `true_entity_id`, `record_type`, and `invalid_kind` for evaluation only;
the pipeline input itself has no label columns.

## `merged_records.csv`
| Column | Description |
|---|---|
| master_id | Deterministic id `M00001`... |
| name, email, phone, address | Golden values chosen by survivorship |
| source_ids | Source `customer_id`s joined with `\|` |
| source_count | Number of source records merged |
| match_reasons | Why records were merged (`exact_email_and_phone`, `similar_name_same_phone`, ...) |
| conflicting_fields | Fields whose source values disagreed |
| run_id, source_file | Pipeline run and source CSV basename |

## `review_queue.csv`
| Column | Description |
|---|---|
| record1, record2 | Source ids of the uncertain pair |
| similarity_score | Name similarity 0-100 (RapidFuzz ratio) |
| reason | `name_below_auto_threshold_same_email/phone` or `similar_name_no_shared_identifier` |
| name_1/2, email_1/2, phone_1/2 | Values shown for the reviewer |

## `rejected_records.csv`
| Column | Description |
|---|---|
| record_id | Source id (blank if missing) |
| reason | `;`-joined: missing_customer_id, duplicate_customer_id, missing_name, missing_email, invalid_email, invalid_phone |
| source_file, source_row, run_id | Original CSV basename, 1-based CSV line number including header, and pipeline run |
| raw_name, raw_email, raw_phone | Original values |

## `lineage.json`
For each master record, this file lists its source records, match reasons, conflicting fields, survivorship
rule, and run ID. In other words, it lets a reviewer trace a merged value back to the records that supplied it.

## `reconciliation_report.csv`
Each row reports one check using `check_name`, `expected`, `actual`, `status` (`PASS`/`FAIL`), and `detail`.
The checks confirm that input rows are accounted for, every valid ID belongs to exactly one master, master
IDs are unique, rejects have reasons, and review-queue IDs point to known records.

## `run_metrics.csv`
Columns: `run_id`, `source_file`, `start_time`, `end_time`, `status`, `failure_reason`, `input_count`,
`valid_count`, `reject_count`, `duplicates_removed`, `merged_masters`, `output_count`, `review_pairs`,
`pairs_compared`, `reconciliation_failures`, and stage/total timings (`ingest_s`, `validate_s`, `detect_s`,
`merge_s`, `publish_s`, `total_s`). Status can be `SUCCESS`, `RECONCILIATION_FAILED`, `FILE_REJECTED`,
or `FAILED`.

## `evaluation_report.json`
This optional report is created by `python -m src.evaluate`. It compares the pipeline results with the
generator's separate synthetic labels and reports pairwise precision and recall, missed matches found in
the review queue, and whether labelled-invalid records were rejected. The labels are for evaluation only;
they are never used as pipeline input.
