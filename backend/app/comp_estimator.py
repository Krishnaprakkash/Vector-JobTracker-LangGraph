import json
import re

from .seniority import detect_seniority
from .comp_cache import get_cached_comp, set_cached_comp
from .rate_limiter import route_call_with_tools
from .tavily_search import tavily_search

SYSTEM_PROMPT = (
    "You are a compensation research assistant. Given a job title, location, and seniority level, "
    "use the web_search tool to find current market salary data, then respond with your estimate. "
    "Once you have search results, respond ONLY with JSON: "
    "{\"comp_min\": int, \"comp_max\": int, \"comp_currency\": \"USD\"}. No prose, no markdown fences."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current salary/compensation data.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]

MAX_TOOL_ITERATIONS = 2


def _parse_llm_json(text: str) -> dict | None:
    cleaned = re.sub(r"```json|```", "", text or "").strip()
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


async def _run_tool_loop(title: str, location: str, seniority: str) -> dict | None:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Title: {title}\nLocation: {location}\nSeniority: {seniority}"},
    ]

    for _ in range(MAX_TOOL_ITERATIONS):
        result = await route_call_with_tools("comp", messages, TOOLS, est_tokens=700, max_tokens=300)
        if result["status"] != "ok":
            return {"status": "quota_exceeded", "reset_at": result.get("reset_at")}

        message = result["message"]
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            parsed = _parse_llm_json(message.get("content", ""))
            return {"status": "ok", "data": parsed} if parsed else {"status": "parse_failed"}

        messages.append(message)
        for call in tool_calls:
            args = json.loads(call["function"]["arguments"])
            search_result = await tavily_search(args.get("query", f"{title} salary {location}"))
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": search_result or "No results found.",
            })

    return {"status": "max_iterations"}


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
    seniority = detect_seniority(title, description) or "Mid"

    cached = await get_cached_comp(title, location, seniority)
    if cached:
        return {**cached, "comp_estimated": True, "status": "ok"}

    outcome = await _run_tool_loop(title, location, seniority)

    if outcome["status"] != "ok" or not outcome.get("data"):
        return {
            "comp_min": None, "comp_max": None, "comp_currency": None,
            "comp_estimated": True, "status": "pending_retry",
        }

    estimated = outcome["data"]
    await set_cached_comp(title, location, seniority, estimated)
    return {**estimated, "comp_estimated": True, "status": "ok"}