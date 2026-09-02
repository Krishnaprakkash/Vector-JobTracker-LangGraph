import json
import re

from .seniority import detect_seniority
from .comp_cache import get_cached_comp, set_cached_comp
from .rate_limiter import route_call

SYSTEM_PROMPT = (
    "You are a compensation research assistant. Given a job title, location, "
    "and seniority level, estimate the current market salary range using web search. "
    "Respond ONLY with JSON: {\"comp_min\": int, \"comp_max\": int, \"comp_currency\": \"USD\"}. "
    "No prose, no markdown fences."
)


def _parse_llm_json(text: str) -> dict | None:
    cleaned = re.sub(r"```json|```", "", text).strip()
    try:
        data = json.loads(cleaned)
        if "comp_min" in data and "comp_max" in data:
            return {
                "comp_min": int(data["comp_min"]),
                "comp_max": int(data["comp_max"]),
                "comp_currency": data.get("comp_currency", "USD"),
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    return None


def _parse_ashby_summary(summary: str | None) -> dict | None:
    if not summary:
        return None
    numbers = re.findall(r"[\d,]+(?:\.\d+)?[KkMm]?", summary)
    if len(numbers) < 2:
        return None

    def to_int(s: str) -> int:
        s = s.replace(",", "")
        if s[-1] in "Kk":
            return int(float(s[:-1]) * 1_000)
        if s[-1] in "Mm":
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))

    try:
        return {"comp_min": to_int(numbers[0]), "comp_max": to_int(numbers[1]), "comp_currency": "USD"}
    except ValueError:
        return None


async def resolve_compensation(job: dict) -> dict:
    """Returns {comp_min, comp_max, comp_currency, comp_estimated, status}.
    status: 'ok' | 'pending_retry'
    """
    parsed = _parse_ashby_summary(job.get("comp_raw_summary"))
    if parsed:
        return {**parsed, "comp_estimated": False, "status": "ok"}

    title = job.get("title", "")
    location = job.get("location", "") or "Remote"
    description = job.get("description", "")
    seniority = detect_seniority(title, description)

    cached = await get_cached_comp(title, location, seniority)
    if cached:
        return {**cached, "comp_estimated": True, "status": "ok"}

    prompt = f"Title: {title}\nLocation: {location}\nSeniority: {seniority}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    result = await route_call("comp", messages, est_tokens=300, max_tokens=200)

    if result["status"] != "ok":
        return {
            "comp_min": None, "comp_max": None, "comp_currency": None,
            "comp_estimated": True, "status": "pending_retry",
            "reset_at": result.get("reset_at"),
        }

    estimated = _parse_llm_json(result["content"])
    if not estimated:
        return {
            "comp_min": None, "comp_max": None, "comp_currency": None,
            "comp_estimated": True, "status": "pending_retry",
        }

    await set_cached_comp(title, location, seniority, estimated)
    return {**estimated, "comp_estimated": True, "status": "ok"}