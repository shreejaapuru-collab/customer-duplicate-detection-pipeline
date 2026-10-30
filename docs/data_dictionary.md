# Data Dictionary

## Input - `customers.csv`
| Column | Required | Description |
|---|---|---|
| customer_id | yes | Unique source record id |
| name | yes | Full name |
| email | yes | Valid email (stored lower-case) |
| phone | no | 10-digit number starting 6-9; `+91`/`0` prefix stripped; null allowed |
| address | no | Free text; carried into the merged record |

The generator writes a separate `customers_<n>_labels.csv` file for evaluation. It contains
`customer_id`, `true_entity_id`, `record_type`, and `invalid_kind`; label columns are not added
to the pipeline input.

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
List of `{master_id, source_records, match_reasons, conflicting_fields, survivorship_rule, run_id}`.

## `reconciliation_report.csv`
One row per check with `check_name`, `expected`, `actual`, `status` (`PASS`/`FAIL`), and `detail`.
Checks include input = valid + rejected, every valid ID assigned to exactly one master, unique master IDs,
explained rejects, and valid review-queue references.

## `run_metrics.csv`
Columns: `run_id`, `source_file`, `start_time`, `end_time`, `status`, `failure_reason`, `input_count`,
`valid_count`, `reject_count`, `duplicates_removed`, `merged_masters`, `output_count`, `review_pairs`,
`pairs_compared`, `reconciliation_failures`, and stage/total timings (`ingest_s`, `validate_s`, `detect_s`,
`merge_s`, `publish_s`, `total_s`). Status can be `SUCCESS`, `RECONCILIATION_FAILED`, `FILE_REJECTED`,
or `FAILED`.

## `evaluation_report.json`
Optional output from `python -m src.evaluate`. Reports pairwise duplicate precision/recall, missed pairs
found in the review queue, and whether labelled-invalid records were rejected. It compares outputs with
the separate synthetic labels file; these labels are evaluation-only, not pipeline input.
