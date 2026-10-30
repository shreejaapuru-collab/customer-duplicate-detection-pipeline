# Customer Duplicate Detection Pipeline

A small, tested data-engineering pipeline that takes customer records, **validates** them,
**finds exact and probable duplicates**, **merges** them with survivorship rules, tracks
**lineage**, and sends uncertain matches to a **manual review queue**.

No ML training and no UI - just a clean, reproducible, idempotent Python pipeline.

```
CSV -> Ingestion -> Validation -> Duplicate Detection -> Survivorship -> Lineage -> Outputs
         |             |(rejects)        |(uncertain)                                 |
     bad schema    rejected_records   review_queue.csv          merged_records / lineage / metrics
```

## Quick start

### Windows PowerShell

Run these commands from the project root (the folder containing `main.py`):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python main.py
python -m pytest -v

python generator.py --rows 10000 --seed 42 --out data/generated/customers_10000.csv
python main.py --input data/generated/customers_10000.csv --output-dir outputs/large
python -m src.evaluate --labels data/generated/customers_10000_labels.csv --outputs outputs/large
```

The generator writes the pipeline input to `customers_10000.csv` and its expected-answer labels
separately to `customers_10000_labels.csv`; labels are never included in the input CSV. The
evaluation command writes `evaluation_report.json` alongside the pipeline outputs. The pipeline
also writes `reconciliation_report.csv` on every successful run.

If PowerShell blocks activation, allow it for the current terminal only, then activate:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python main.py
python -m pytest -v

python generator.py --rows 10000 --seed 42 --out data/generated/customers_10000.csv
python main.py --input data/generated/customers_10000.csv --output-dir outputs/large
python -m src.evaluate --labels data/generated/customers_10000_labels.csv --outputs outputs/large
```

## Project structure

```
main.py              CLI entry point
generator.py         synthetic data generator (seeded, scalable)
src/
  ingestion.py       read CSV, schema check (missing column => file rejected)
  validation.py      normalise + validate rows -> valid / rejected
  similarity.py      RapidFuzz Levenshtein-style similarity (with pure-Python fallback)
  duplicate_detection.py   blocking + pair scoring + clustering + review queue
  survivorship.py    golden-record rules
  lineage.py         master_id -> source_records
  reconcile.py       source-to-target count and key checks
  evaluate.py        compare results with generator ground-truth labels
  publish.py         atomic CSV/JSON writers, metrics upsert
  pipeline.py        orchestrates all stages
  logger.py          console + logs/pipeline.log
tests/               pytest suite (validation, duplicates, retries, edge cases, evaluation)
data/sample/         small hand-made dataset (covers every case)
outputs/             sample results; outputs/large/ holds the 10k run
docs/                architecture.md, data_dictionary.md
```

## Matching rules

| Condition | Result |
|---|---|
| same email **and** same phone | **auto-merge** (exact) |
| name similarity >= 90 **and** same email *or* phone | **auto-merge** |
| name similarity 75-90 and same email or phone | **review queue** |
| name similarity >= 88, nothing else shared | **review queue** |
| anything else | not a match |

Name similarity = `rapidfuzz.fuzz.ratio` on lower-cased, punctuation-free names (0-100).
Examples: `John Smith` vs `Jon Smith` = 94.7, `John Smith` vs `John Smyth` = 90.0.
Thresholds live in `MatchConfig` (`src/duplicate_detection.py`) and can be tuned.

**Survivorship** (per field): ignore nulls -> most frequent value -> value from the most complete
record -> lowest `customer_id`. Fields that disagreed are listed in `conflicting_fields`.

## Outputs (`outputs/`)

| File | Contents |
|---|---|
| `merged_records.csv` | one golden record per person: master_id, name, email, phone, address, source_ids, ... |
| `review_queue.csv` | record1, record2, similarity_score, reason (+ names/emails/phones for the reviewer) |
| `rejected_records.csv` | record_id, reason (+ raw values) |
| `lineage.json` | `{"master_id": "M00001", "source_records": ["C001","C002","C003"], ...}` |
| `reconciliation_report.csv` | checks that input rows reconcile, valid IDs appear in exactly one master, and review IDs are valid |
| `run_metrics.csv` | run_id, source_file, start/end time, status/failure reason, counts, timings, ... |
| `evaluation_report.json` | optional quality metrics from comparison with synthetic ground-truth labels |

Console/log summary, e.g.:
```
run_id=run_1dea43ce02   input_rows=16   valid_rows=13   rejected_rows=3
duplicates=3            merged_records=2   output_records=10   review_pairs=3
```

## Data validation rules

* `customer_id` required and unique (first occurrence kept)
* `name` required; `email` required and well-formed
* `phone` is optional (null is allowed so survivorship can fill it from a duplicate), but if present it must
  be a valid 10-digit number starting 6-9 (`+91` / leading `0` are stripped)
* Missing required **column** => the whole file is rejected (exit code 2); header-only / empty file => 0 records, no crash

## Idempotency

* Outputs are rewritten atomically (temp file + rename), never appended.
* `master_id`s are deterministic (sorted by smallest source id).
* `run_id` is a hash of input content + config, so re-running the same input replaces its metrics row.
* Running `python main.py` twice gives byte-identical data outputs (tested). Only the timestamps in
  `run_metrics.csv` change.
* Each output file is replaced atomically, but publishing the set of output files is not one transaction.
  If a run fails partway through publishing, rerun the same input with the same output directory; this
  regenerates and replaces all outputs. The automated suite simulates a mid-publish failure and retry.

## Synthetic data

`generator.py` creates reproducible (seeded) data: 75% unique customers, 10% exact duplicates (some with a
blanked phone to exercise survivorship), 10% probable duplicates (John/Jon, Katherine/Kathryn, typos; share
phone, email, or nothing) and 5% invalid rows (missing name, null email, invalid phone). Uses Faker when installed.
All data is synthetic, so there are no reuse-rights concerns.

## Performance check

Measure the full pipeline on a reproducible 10,000-row generated batch in PowerShell:

```powershell
python generator.py --rows 10000 --seed 42 --out "$env:TEMP\customers_10000.csv"
$elapsed = Measure-Command {
    python main.py --input "$env:TEMP\customers_10000.csv" `
        --output-dir "$env:TEMP\dedup-output" --log-dir "$env:TEMP\dedup-logs"
}
"Elapsed: {0:N2} seconds" -f $elapsed.TotalSeconds
```

Record the elapsed time reported on your machine along with the Python version and whether
RapidFuzz is installed; runtime varies by hardware and matcher backend. The generator is deterministic
for a fixed seed, so the input remains reproducible.

One measured run in the development environment: Python 3.13.3, RapidFuzz, 10,000 input rows
(9,500 valid, 500 rejected), 7,613 output masters, **2.58 seconds**. Treat this as a reference
measurement, not a performance guarantee; hardware and dependency versions affect runtime.

## Scalability notes

Comparing every pair is O(n^2). The pipeline uses **blocking**: only records sharing a phone, an email, or the
same (first-initial, last-initial) of the name are compared. RapidFuzz speeds up scoring of candidate
pairs; a reasonable next optimization for large volumes is distributed blocking (Spark/Dask) or a
database-side join on blocking keys.

## Known limitations / assumptions

* Matching is name/email/phone only; addresses are carried through but not used to match.
* Clusters are formed transitively (A~B and B~C => A, B, C merge), a standard trade-off; review-queue pairs are
  never auto-merged.
* A typo in the *first letter* of both first and last name is only caught if phone or email is shared (blocking trade-off).
* Two different people with identical names and no shared identifier go to the review queue by design.
