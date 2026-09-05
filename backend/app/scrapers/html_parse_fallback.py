import re
import json
import httpx

from ..rate_limiter import route_call

JOB_SIGNAL_WORDS = ["apply", "responsibilities", "qualifications", "job description", "requirements"]
BLOCKED_DOMAINS = ["linkedin.com", "indeed.com", "glassdoor.com"]

PARSE_SYSTEM_PROMPT = (
    "Extract job posting details from this webpage text. "
    "Respond ONLY with JSON: {\"title\": str, \"company\": str, \"description\": str}. "
    "Use empty string for any field you cannot determine. "
    "If this is clearly not a job posting, respond with {\"title\": \"\", \"company\": \"\", \"description\": \"\"}. "
    "No prose, no markdown fences."
)

CONTENT_PATTERNS = [
    re.compile(r'<main[^>]*>(.*?)</main>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<article[^>]*>(.*?)</article>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<div[^>]*class="[^"]*job[^"]*description[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<div[^>]*id="[^"]*job[^"]*description[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
]


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_main_content(html: str) -> str:
    for pattern in CONTENT_PATTERNS:
        match = pattern.search(html)
        if match and len(match.group(1)) > 200:
            return _strip_html(match.group(1))
    return _strip_html(html)


def _looks_like_job_posting(text: str) -> bool:
    lower = text.lower()
    return sum(1 for w in JOB_SIGNAL_WORDS if w in lower) >= 2


def _extract_json_ld_job(html: str) -> dict | None:
    matches = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for raw in matches:
        try:
            data = json.loads(raw.strip())
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if item.get("@type") == "JobPosting":
                    return {
                        "title": item.get("title", ""),
                        "company": (item.get("hiringOrganization") or {}).get("name", ""),
                        "description": re.sub(r"<[^>]+>", " ", item.get("description", ""))[:3000],
                    }
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


async def parse_job_from_url(url: str) -> dict | None:
    if any(domain in url for domain in BLOCKED_DOMAINS):
        return None

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
        resp.raise_for_status()
    except Exception:
        return None

    # try structured JobPosting schema first — free, no LLM call, more reliable
    json_ld = _extract_json_ld_job(resp.text)
    if json_ld and json_ld.get("title"):
        return {**json_ld, "url": url, "source": "html_parse"}

    # fallback: heuristic pre-filter + LLM parsing
    text = _extract_main_content(resp.text)[:4000]
    if not _looks_like_job_posting(text):
        return None

    messages = [
        {"role": "system", "content": PARSE_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    result = await route_call("html_parse", messages, est_tokens=1200, max_tokens=500)
    if result["status"] != "ok":
        return None

    try:
        data = json.loads(re.sub(r"```json|```", "", result["content"]).strip())
        if data.get("title"):
            return {
                "title": data["title"],
                "company": data.get("company") or "unknown",
                "description": data.get("description") or "",
                "url": url,
                "source": "html_parse",
            }
    except json.JSONDecodeError:
        return None
    return None