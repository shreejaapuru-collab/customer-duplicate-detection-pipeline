import csv
import tempfile
from pathlib import Path

HEADER = ["customer_id", "name", "email", "phone"]


def write_csv(directory, rows, header=HEADER, name="customers.csv") -> Path:
    path = Path(directory) / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def tmpdir():
    return tempfile.TemporaryDirectory()
