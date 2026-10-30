"""String similarity. Uses RapidFuzz; falls back to a pure-Python equivalent.

fuzz.ratio is a normalised Indel (Levenshtein-style) similarity on a 0-100 scale:
    100 * (1 - indel_distance / (len(a) + len(b)))
The fallback computes exactly the same number, so results are identical either way.
"""
try:
    from rapidfuzz import fuzz

    BACKEND = "rapidfuzz"

    def name_similarity(a: str, b: str) -> float:
        return float(fuzz.ratio(a, b))

except ImportError:  # pragma: no cover - only when rapidfuzz isn't installed
    BACKEND = "pure-python fallback"

    def _lcs_len(a: str, b: str) -> int:
        prev = [0] * (len(b) + 1)
        for ca in a:
            cur = [0]
            for j, cb in enumerate(b, 1):
                cur.append(prev[j - 1] + 1 if ca == cb else max(prev[j], cur[-1]))
            prev = cur
        return prev[-1]

    def name_similarity(a: str, b: str) -> float:
        if not a and not b:
            return 100.0
        return 100.0 * 2 * _lcs_len(a, b) / (len(a) + len(b))
