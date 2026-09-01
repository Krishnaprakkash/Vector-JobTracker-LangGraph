import hashlib
import re


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", "", text)


def compute_job_hash(company: str, title: str) -> str:
    key = _normalize(company) + _normalize(title)
    return hashlib.md5(key.encode()).hexdigest()