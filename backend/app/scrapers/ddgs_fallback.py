# backend/app/scrapers/ddgs_fallback.py
import re
from ddgs import DDGS

TIMEOUT = 5.0
ATS_FILTER = "site:boards.greenhouse.io OR site:jobs.lever.co OR site:jobs.ashbyhq.com"

SLUG_PATTERNS = [
    (re.compile(r"boards\.greenhouse\.io/([^/]+)/"), "greenhouse"),
    (re.compile(r"jobs\.lever\.co/([^/]+)/"), "lever"),
    (re.compile(r"jobs\.ashbyhq\.com/([^/]+)/"), "ashby"),
]


def extract_company_slug(url: str) -> tuple[str, str] | None:
    for pattern, ats_name in SLUG_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1), ats_name
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
        parsed = extract_company_slug(url)
        if not parsed:
            continue
        company, ats_name = parsed
        jobs.append({
            "title": r.get("title", ""),
            "company": company,
            "location": None,
            "description": r.get("body", ""),
            "url": url,
            "source": ats_name,  # now the real ATS, not literal "ddgs"
        })
    return jobs


def relax_query(role_query: str) -> str:
    words = role_query.split()
    return " ".join(words[:2]) if len(words) > 2 else role_query

def search_jobs_ddgs_general(role_query: str, max_results: int = 20) -> list[str]:
    """Returns raw URLs, no site: filter — used as source for html_parse fallback."""
    query = f"{role_query} jobs"
    try:
        with DDGS(timeout=TIMEOUT) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []
    return [r.get("href", "") for r in results if r.get("href")]