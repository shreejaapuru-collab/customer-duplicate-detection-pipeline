# Data Dictionary

## Input - `customers.csv`
| Column | Required | Description |
|---|---|---|
| customer_id | yes | Unique source record id |
| name | yes | Full name |
| email | yes | Valid email (stored lower-case) |
| phone | no | 10-digit number starting 6-9; `+91`/`0` prefix stripped; null allowed |
| address | no | Free text; carried into the merged record |

## `merged_records.csv`
| Column | Description |
|---|---|
| master_id | Deterministic id `M00001`... |
| name, email, phone, address | Golden values chosen by survivorship |
| source_ids | Source `customer_id`s joined with `\|` |
| source_count | Number of source records merged |
| match_reasons | Why records were merged (`exact_email_and_phone`, `similar_name_same_phone`, ...) |
| conflicting_fields | Fields whose source values disagreed |

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
| raw_name, raw_email, raw_phone | Original values |

## `lineage.json`
List of `{master_id, source_records, match_reasons, conflicting_fields, survivorship_rule, run_id}`.

## `run_metrics.csv`
`run_id, start_time, end_time, status (SUCCESS|FILE_REJECTED), input_count, valid_count, reject_count,
duplicates_removed (valid - output), merged_masters (masters built from >1 record), output_count, review_pairs`
