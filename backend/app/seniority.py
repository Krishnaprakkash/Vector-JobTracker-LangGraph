import re

TITLE_LEVEL_PATTERNS = [
    (r"\b(intern|internship)\b", "Intern"),
    (r"\b(jr|junior)\b", "Junior"),
    (r"\b(sr|senior)\b", "Senior"),
    (r"\b(staff)\b", "Staff"),
    (r"\b(principal)\b", "Principal"),
    (r"\b(lead)\b", "Lead"),
    (r"\b(director)\b", "Director"),
    (r"\b(vp|vice president)\b", "VP"),
]

YEARS_PATTERN = re.compile(
    r"(\d+)\+?\s*(?:-|to)?\s*(\d+)?\+?\s*years?\s*(?:of\s+)?experience",
    re.IGNORECASE,
)


def _bucket_from_years(min_years: int) -> str:
    if min_years <= 1:
        return "Entry"
    if min_years <= 4:
        return "Mid"
    if min_years <= 8:
        return "Senior"
    return "Staff"


def detect_seniority(title: str, description: str = "") -> str | None:
    title_lower = title.lower()
    for pattern, label in TITLE_LEVEL_PATTERNS:
        if re.search(pattern, title_lower):
            return label

    match = YEARS_PATTERN.search(description or "")
    if match:
        min_years = int(match.group(1))
        return _bucket_from_years(min_years)

    return None