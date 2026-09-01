# backend/app/scrapers/ddgs_fallback.py
import re
from ddgs import DDGS

TIMEOUT = 5.0
ATS_FILTER = "site:boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.ashbyhq.com"

SLUG_PATTERNS = [
    re.compile(r"boards\.greenhouse\.io/([^/]+)/"),
    re.compile(r"jobs\.lever\.co/([^/]+)/"),
    re.compile(r"jobs\.ashbyhq\.com/([^/]+)/"),
]


def extract_company_slug(url: str) -> str | None:
    for pattern in SLUG_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def search_jobs_ddgs(role_query: str, max_results: int = 20) -> list[dict]:
    query = f"{role_query} jobs {ATS_FILTER}"

    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []

    jobs = []
    for r in results:
        url = r.get("href", "")
        company = extract_company_slug(url)
        jobs.append({
            "title": r.get("title", ""),
            "company": company,
            "location": None,
            "description": r.get("body", ""),
            "url": url,
            "source": "ddgs",
        })
    return [j for j in jobs if j["company"]]  # drop unparseable results


def relax_query(role_query: str) -> str:
    words = role_query.split()
    return " ".join(words[:2]) if len(words) > 2 else role_query