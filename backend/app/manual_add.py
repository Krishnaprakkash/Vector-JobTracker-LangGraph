import json
import re
from html import unescape

from bs4 import BeautifulSoup

from .rate_limiter import route_call
from .tavily_search import tavily_search
from .comp_estimator import resolve_compensation
from .scoring import extract_job_requirements, score_job_fit, _get_top_resume_chunks


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


async def enrich_manual_job(
    db,
    title: str,
    location: str | None,
    description: str | None,
    resume_id,
    comp_min: int | None,
    comp_max: int | None,
) -> dict:
    """Comp estimation + fit scoring for manually/Notion-added jobs.
    Returns a dict of fields to merge into the Job row; empty keys are simply omitted."""
    result = {}

    if comp_min is None and comp_max is None:
        comp = await resolve_compensation({"title": title, "location": location, "description": description})
        result["comp_min"] = comp.get("comp_min")
        result["comp_max"] = comp.get("comp_max")
        result["comp_currency"] = comp.get("comp_currency")
        result["comp_estimated"] = comp.get("comp_estimated", True)

    if description and resume_id:
        extracted = await extract_job_requirements(description)
        resume_chunks = await _get_top_resume_chunks(db, resume_id, description)
        score_result = await score_job_fit(title, description, extracted, resume_chunks)
        if score_result:
            result["match_score"] = score_result["match_score"]
            result["match_rationale"] = score_result["match_rationale"]

    return result