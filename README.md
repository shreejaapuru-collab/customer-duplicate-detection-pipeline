# Customer Duplicate Detection Pipeline

Customer data often arrives with spelling differences, repeated contact details, and incomplete fields. This
Python project takes a CSV of customer records, checks it, finds likely duplicates, and creates a cleaned
set of customer records. When a match is uncertain, it leaves the records separate and adds the pair to a
review queue instead of merging them automatically.

The pipeline is intentionally local and straightforward to run. Its main focus is a reproducible 10,000-row
batch, with transparent matching rules, source lineage, and reports that make the results easier to check.

## What happens to the data

```text
Customer CSV
    |
    v
Read and check the schema
    |
    v
Validate and normalize records ------> rejected_records.csv
    |
    v
Find matches ------------------------> review_queue.csv (uncertain pairs)
    |
    v
Build customer records and lineage
    |
    +--------------------------------> merged_records.csv
    +--------------------------------> lineage.json
    +--------------------------------> reconciliation_report.csv
    +--------------------------------> run_metrics.csv
```

## Get started

Run the following commands from the project folder (the folder containing `main.py`).

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python main.py
python -m pytest -v
```

If PowerShell prevents environment activation, allow it for this terminal session and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python main.py
python -m pytest -v
```

The first command runs the small sample in `data/sample/customers.csv`. Results go to `outputs/`, and
the run log is written to `logs/pipeline.log`.

## Try a 10,000-row run

The seeded generator makes the input reproducible and writes evaluation labels to a separate file. Those
labels are not included in the CSV passed to the pipeline.

```powershell
python generator.py --rows 10000 --seed 42 --out data/generated/customers_10000.csv
python main.py --input data/generated/customers_10000.csv --output-dir outputs/large
python -m src.evaluate --labels data/generated/customers_10000_labels.csv --outputs outputs/large
```

The evaluation command writes `evaluation_report.json`. The pipeline creates a
`reconciliation_report.csv` for each successful run. See [docs/data_dictionary.md](docs/data_dictionary.md)
for the fields in each file.

## How matching works

The pipeline uses name, email, and phone. Addresses are carried into the final records but do not influence
matching.

| What the records have in common | What the pipeline does |
|---|---|
| Same email and same phone | Merge as an exact match |
| Name similarity of at least 90 and a shared email or phone | Merge |
| Name similarity of at least 75 and a shared email or phone, but below the merge threshold | Send to review |
| Name similarity of at least 88 with no shared identifier | Send to review |
| None of the above | Keep separate |

Name similarity is calculated with RapidFuzz when installed, with a pure-Python fallback. The thresholds
are configurable through `MatchConfig` and the command-line options.

When records are merged, the pipeline chooses values field by field: it ignores nulls, uses the most
frequent remaining value, then breaks ties using the most complete record and the lowest customer ID.
Disagreements are recorded in `conflicting_fields`.

## Files produced

The default run writes these files under `outputs/` (or under the directory passed with `--output-dir`):

| File | What you can use it for |
|---|---|
| `merged_records.csv` | One surviving customer record per detected group, with source IDs and match details |
| `review_queue.csv` | Candidate pairs that need a person to decide |
| `rejected_records.csv` | Invalid rows, their validation reasons, and source locations |
| `lineage.json` | The source records and match details behind each master record |
| `reconciliation_report.csv` | Checks that input rows, valid records, rejects, and master records balance |
| `run_metrics.csv` | Run ID, source file, status, counts, failure reason, and timings |
| `evaluation_report.json` | Optional comparison with the generator's separate expected-answer labels |

For a quick check of the sample run, expect 16 input rows: 13 valid and 3 rejected. The result has 10 master
records and 3 review pairs. The 10k run's checked-in outputs and reports are under `outputs/large/`.

## Safe reruns and recovery

The run ID is based on the input contents and matching configuration. Running the same input again replaces
that run's metrics entry instead of adding a duplicate. Master IDs and data outputs are deterministic for
the same input and configuration.

Each output file is written atomically, and the metrics file is written last. The set of files is not one
transaction, though. If a run fails while publishing, check `run_metrics.csv` for the failure and rerun the
same input with the same output directory. A rerun regenerates and replaces the output files. This project
processes each input as a full snapshot; it does not maintain incremental history for late-arriving updates.

## Tests and performance

Run the full test suite with:

```powershell
python -m pytest -v
```

The tests cover validation, empty and malformed inputs, duplicate matching, survivorship, lineage,
idempotency, retry after a simulated failure, generator reproducibility, and checks against generated
ground-truth labels.

To time a 10,000-row run in PowerShell:

```powershell
python generator.py --rows 10000 --seed 42 --out "$env:TEMP\customers_10000.csv"
$elapsed = Measure-Command {
    python main.py --input "$env:TEMP\customers_10000.csv" `
        --output-dir "$env:TEMP\dedup-output" --log-dir "$env:TEMP\dedup-logs"
}
"Elapsed: {0:N2} seconds" -f $elapsed.TotalSeconds
```

A recorded run with Python 3.13.3 and RapidFuzz processed 10,000 rows (9,500 valid, 500 rejected) and
produced 7,613 master records in 2.58 seconds. This is one machine's result, not a runtime guarantee.
Blocking avoids comparing every record pair; for larger workloads, distributed or database-side blocking
would be a reasonable next step. The intended and measured target here is 10,000 rows; performance at
100,000 rows has not been measured.

## Project layout

```text
main.py                 Command-line entry point
generator.py            Seeded customer data and separate evaluation labels
src/                    Pipeline, validation, matching, lineage, and reporting modules
tests/                  Automated tests
data/sample/            Small example input
outputs/                Sample results and the 10k run evidence
docs/                   Architecture and data dictionary
design_tradeoffs.md     Matching, recovery, and performance decisions
```

## Assumptions and limitations

- Email is required; phone and address are optional. Phone values are normalized as Indian mobile numbers.
- Matching does not use address information.
- Matching clusters are transitive: if A matches B and B matches C, all three join the same master. A bad
  link can therefore over-merge records; uncertain pairs are kept out of the clusters.
- Name-only review suggestions depend on the name blocking keys. Typos in both the first and last initials
  may not be found unless an email or phone is shared.
- The records are held in memory. A much larger workload would need a different processing approach.
- This is a single-customer-file pipeline, so cross-table reference-key checks do not apply.

For more on the pipeline stages and trade-offs, see [docs/architecture.md](docs/architecture.md) and
[design_tradeoffs.md](design_tradeoffs.md).
