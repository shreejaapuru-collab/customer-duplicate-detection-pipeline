"""Synthetic customer data generator (reproducible via --seed, scales to any --rows).

    python generator.py --rows 1000 --seed 42 --out data/generated/customers_1000.csv

Composition (defaults):
    10%  exact duplicates     same email + phone as an existing person (sometimes phone blanked)
    10%  probable duplicates  name variants (John/Jon, Katherine/Kathryn, typos) that share
                              phone OR email OR nothing  -> auto-merge or review queue
     5%  invalid rows         missing name / null email / invalid phone
    75%  unique customers
All data is synthetic (Faker if installed, otherwise built-in name lists).
"""
import argparse
import csv
import random
from pathlib import Path

try:
    from faker import Faker
    _HAS_FAKER = True
except ImportError:  # pragma: no cover
    _HAS_FAKER = False

FALLBACK_FIRST = [
    "John", "Katherine", "Michael", "Sarah", "Jennifer", "Steven", "Alice", "Robert", "Priya", "Ramesh",
    "Meera", "Arjun", "Sneha", "Vikram", "Anita", "Rahul", "Kavya", "Suresh", "Divya", "Karthik",
    "Pooja", "Amit", "Neha", "Rohit", "Lakshmi", "Manoj", "Swathi", "Naveen", "Deepa", "Harish",
    "Anjali", "Varun", "Sandeep", "Ritu", "Mahesh", "Isha", "Tarun", "Bhavna", "Gopal", "Nisha",
    "David", "Emily", "Daniel", "Olivia", "James", "Sophia", "Thomas", "Grace", "Peter", "Laura"]
FALLBACK_LAST = [
    "Smith", "Johnson", "Brown", "Taylor", "Sharma", "Reddy", "Kumar", "Iyer", "Rao", "Singh",
    "Patel", "Nair", "Gupta", "Mehta", "Das", "Verma", "Naidu", "Joshi", "Menon", "Pillai",
    "Chowdhury", "Banerjee", "Kapoor", "Malhotra", "Bhat", "Shetty", "Agarwal", "Saxena", "Trivedi", "Chopra",
    "Wilson", "Clark", "Lewis", "Walker", "Hall", "Young", "King", "Wright", "Scott", "Green"]
FALLBACK_STREETS = ["MG Road", "Park Street", "Lake View", "Banjara Hills", "Indiranagar", "Koramangala"]
FALLBACK_CITIES = ["Hyderabad", "Mumbai", "Pune", "Bengaluru", "Chennai", "Delhi"]

NICKNAMES = {"john": "Jon", "katherine": "Kathryn", "catherine": "Kathrine", "michael": "Micheal",
             "steven": "Stephen", "sarah": "Sara", "jennifer": "Jenifer", "christopher": "Cristopher",
             "elizabeth": "Elisabeth", "alexander": "Alexandar", "ramesh": "Rameshh", "priya": "Pria"}
DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
FIELDS = ["customer_id", "name", "email", "phone", "address"]
LABEL_FIELDS = ["customer_id", "true_entity_id", "record_type", "invalid_kind"]


class Generator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.used_names: set[str] = set()
        self.used_emails: set[str] = set()
        self.used_phones: set[str] = set()
        if _HAS_FAKER:
            Faker.seed(seed)
            self.fake = Faker("en_IN")

    # ---- building blocks -------------------------------------------------
    def _name(self) -> str:
        if _HAS_FAKER:
            return f"{self.fake.first_name()} {self.fake.last_name()}"
        return f"{self.rng.choice(FALLBACK_FIRST)} {self.rng.choice(FALLBACK_LAST)}"

    def _unique_name(self) -> str:
        """Avoid two different customers sharing a name (that would flood the review queue)."""
        for _ in range(30):
            name = self._name()
            if name not in self.used_names:
                break
        else:  # pool exhausted (fallback lists only) -> add a second surname
            while name in self.used_names:
                name = f"{name} {self.rng.choice(FALLBACK_LAST)}"
        self.used_names.add(name)
        return name

    def _address(self) -> str:
        if _HAS_FAKER:
            return self.fake.address().replace("\n", ", ")
        return (f"{self.rng.randint(1, 99)} {self.rng.choice(FALLBACK_STREETS)}, "
                f"{self.rng.choice(FALLBACK_CITIES)}")

    def _phone(self) -> str:
        while True:
            phone = str(self.rng.choice("6789")) + "".join(self.rng.choices("0123456789", k=9))
            if phone not in self.used_phones:
                self.used_phones.add(phone)
                return phone

    def _email(self, name: str) -> str:
        base = "".join(c for c in name.lower().replace(" ", ".") if c.isalnum() or c == ".")
        while True:
            email = f"{base}{self.rng.randint(1, 9999)}@{self.rng.choice(DOMAINS)}"
            if email not in self.used_emails:
                self.used_emails.add(email)
                return email

    def _typo(self, name: str) -> str:
        """Return a slightly different spelling of the name."""
        first, _, rest = name.partition(" ")
        if first.lower() in NICKNAMES and self.rng.random() < 0.5:
            return f"{NICKNAMES[first.lower()]} {rest}".strip()
        for _ in range(10):
            parts = name.split(" ")
            k = self.rng.randrange(len(parts))
            w = parts[k]
            if len(w) <= 3:
                continue
            pos = self.rng.randrange(1, len(w) - 1)
            op = self.rng.choice(["drop", "swap", "sub"])
            if op == "drop":
                w2 = w[:pos] + w[pos + 1:]
            elif op == "swap":
                w2 = w[:pos] + w[pos + 1] + w[pos] + w[pos + 2:]
            else:
                w2 = w[:pos] + self.rng.choice("aeiouy") + w[pos + 1:]
            if w2 != w:
                parts[k] = w2
                return " ".join(parts)
        return name

    # ---- record factories ------------------------------------------------
    def unique(self) -> dict:
        name = self._unique_name()
        return {"name": name, "email": self._email(name), "phone": self._phone(),
                "address": self._address()}

    def exact_dup(self, base: dict) -> dict:
        rec = dict(base)
        rec["name"] = base["name"].upper() if self.rng.random() < 0.15 else base["name"]
        rec["address"] = "" if self.rng.random() < 0.4 else base["address"]
        if self.rng.random() < 0.3:
            rec["phone"] = ""      # null phone -> survivorship should fill it from the other record
        return rec

    def probable_dup(self, base: dict) -> dict:
        name = self._typo(base["name"])
        roll = self.rng.random()
        email, phone = (self._email(name), self._phone())  # default: nothing shared
        if roll < 0.45:
            phone = base["phone"]       # shares phone only
        elif roll < 0.90:
            email = base["email"]       # shares email only
        return {"name": name, "email": email, "phone": phone, "address": base["address"]}

    def invalid(self) -> dict:
        rec = self.unique()
        kind = self.rng.choice(["no_name", "no_email", "bad_phone"])
        rec["_invalid_kind"] = kind
        if kind == "no_name":
            rec["name"] = ""
        elif kind == "no_email":
            rec["email"] = ""
        else:
            rec["phone"] = self.rng.choice(["12345", "98765", "abcdefghij", "00000"])
        return rec


def generate(rows: int, seed: int = 42, exact_rate: float = 0.10,
             probable_rate: float = 0.10, invalid_rate: float = 0.05) -> list[dict]:
    g = Generator(seed)
    n_exact, n_prob, n_inv = int(rows * exact_rate), int(rows * probable_rate), int(rows * invalid_rate)
    n_unique = max(rows - n_exact - n_prob - n_inv, 1)

    base = [g.unique() for _ in range(n_unique)]
    for k, rec in enumerate(base, start=1):
        rec["_entity"], rec["_type"] = f"E{k:06d}", "unique"
    out = list(base)
    for _ in range(n_exact):
        b = g.rng.choice(base)
        rec = g.exact_dup(b)
        rec["_entity"], rec["_type"] = b["_entity"], "exact_duplicate"
        out.append(rec)
    for _ in range(n_prob):
        b = g.rng.choice(base)
        rec = g.probable_dup(b)
        rec["_entity"], rec["_type"] = b["_entity"], "probable_duplicate"
        out.append(rec)
    for k in range(n_inv):
        rec = g.invalid()
        rec["_entity"], rec["_type"] = f"X{k + 1:06d}", "invalid"
        out.append(rec)
    g.rng.shuffle(out)
    for i, rec in enumerate(out, start=1):
        rec["customer_id"] = f"C{i:06d}"
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Generate synthetic customer data")
    p.add_argument("--rows", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--exact-rate", type=float, default=0.10)
    p.add_argument("--probable-rate", type=float, default=0.10)
    p.add_argument("--invalid-rate", type=float, default=0.05)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    out = Path(args.out or f"data/generated/customers_{args.rows}.csv")
    records = generate(args.rows, args.seed, args.exact_rate, args.probable_rate, args.invalid_rate)
    write_dataset(records, out)
    print(f"wrote {len(records)} rows -> {out} (faker={'yes' if _HAS_FAKER else 'no, fallback lists'})")


def write_dataset(records: list[dict], out: Path) -> Path:
    """Write the input CSV and, SEPARATELY, the expected-answer labels file next to it."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in FIELDS} for r in records)
    labels = out.with_name(out.stem + "_labels.csv")
    with open(labels, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(LABEL_FIELDS)
        for r in records:
            writer.writerow([r["customer_id"], r["_entity"], r["_type"], r.get("_invalid_kind", "")])
    return labels


if __name__ == "__main__":
    main()
