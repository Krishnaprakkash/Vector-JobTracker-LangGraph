import json
import re
from html import unescape

from bs4 import BeautifulSoup

from .rate_limiter import route_call
from .tavily_search import tavily_search


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _extract_location(job: dict) -> str | None:
    loc = job.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
            parts = [p for p in parts if p]
            if parts:
                return ", ".join(parts)
    remote = job.get("applicantLocationRequirements")
    if remote:
        return "Remote"
    return None


def _find_jobposting(node) -> dict | None:
    if isinstance(node, dict):
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "JobPosting" in types:
            return node
        for v in node.values():
            found = _find_jobposting(v)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_jobposting(item)
            if found:
                return found
    return None


def extract_jsonld_jobposting(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        job = _find_jobposting(data)
        if not job:
            continue
        org = job.get("hiringOrganization")
        company = org.get("name") if isinstance(org, dict) else None
        return {
            "title": job.get("title"),
            "company": company,
            "description": _strip_html(job.get("description", ""))[:5000] or None,
            "location": _extract_location(job),
        }
    return None


async def tavily_search_summarize(title: str, company: str, years_experience: int | None) -> str:
    query = f"{title} {company} job responsibilities requirements"
    if years_experience is not None:
        query += f" {years_experience} years experience"

    context = await tavily_search(query, max_results=5)
    if not context:
        return ""

    prompt = (
        f"Summarize the responsibilities and key required skills for this role in 3-4 sentences. "
        f"Role: {title} at {company}.\n\nSearch results:\n{context}"
    )
    result = await route_call("score_reason", [{"role": "user", "content": prompt}], est_tokens=800, max_tokens=300)
    if result["status"] != "ok":
        return ""
    return result["content"].strip()[:2000]