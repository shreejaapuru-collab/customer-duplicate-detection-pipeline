"""Stage 2 - Validation + normalisation. Splits rows into valid / rejected."""
import re

import pandas as pd

NULL_TOKENS = {"", "null", "none", "nan", "n/a", "nil", "-"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")

VALID_COLUMNS = ["customer_id", "name", "email", "phone", "address", "name_key"]
REJECT_COLUMNS = ["record_id", "reason", "raw_name", "raw_email", "raw_phone"]


def clean_text(value) -> str | None:
    """Trim, collapse whitespace, turn null-like tokens into None."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return None if text.lower() in NULL_TOKENS else text


def normalize_phone(value) -> str | None:
    """Digits only; strips +91 / leading 0. Returns None if there is no phone."""
    text = clean_text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def is_valid_phone(digits: str) -> bool:
    """10 digits, starting 6-9 (Indian mobile format)."""
    return len(digits) == 10 and digits[0] in "6789"


def name_key(name: str) -> str:
    """Lower-cased, punctuation-free name used for matching."""
    return " ".join(re.sub(r"[^\w ]", "", name.lower()).split())


def validate_records(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (valid_df, rejected_df).

    Rules
    -----
    * customer_id required and unique (first occurrence wins)
    * name required
    * email required and well-formed (stored lower-case)
    * phone OPTIONAL (null is allowed so survivorship can fill it later),
      but if present it must be a valid 10-digit number
    """
    valid_rows, rejected_rows = [], []
    seen_ids: set[str] = set()

    for rec in df.to_dict("records"):
        cid = clean_text(rec.get("customer_id"))
        name = clean_text(rec.get("name"))
        email = clean_text(rec.get("email"))
        raw_phone = clean_text(rec.get("phone"))
        address = clean_text(rec.get("address"))

        reasons = []
        if cid is None:
            reasons.append("missing_customer_id")
        elif cid in seen_ids:
            reasons.append("duplicate_customer_id")
        if name is None:
            reasons.append("missing_name")
        if email is None:
            reasons.append("missing_email")
        elif not EMAIL_RE.match(email):
            reasons.append("invalid_email")

        phone = None
        if raw_phone is not None:
            phone = normalize_phone(raw_phone)
            if not is_valid_phone(phone):
                reasons.append("invalid_phone")

        if reasons:
            rejected_rows.append({
                "record_id": cid or "",
                "reason": ";".join(reasons),
                "raw_name": rec.get("name", ""),
                "raw_email": rec.get("email", ""),
                "raw_phone": rec.get("phone", ""),
            })
            continue

        seen_ids.add(cid)
        valid_rows.append({
            "customer_id": cid,
            "name": name,
            "email": email.lower(),
            "phone": phone,
            "address": address,
            "name_key": name_key(name),
        })

    valid = pd.DataFrame(valid_rows, columns=VALID_COLUMNS)
    rejected = pd.DataFrame(rejected_rows, columns=REJECT_COLUMNS)
    return valid, rejected
