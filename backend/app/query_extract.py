import json
import re

from .rate_limiter import route_call

SYSTEM_PROMPT = """
You are a precise job query extraction engine. Parse the user's job search query into a structured JSON object.

Extraction Rules:
1. "company": Extract specific organization or company names mentioned (e.g., "Google", "Microsoft"). Set to null if not specified.
2. "location": Extract geographic entities (cities, countries, regions, "Remote"). Set to null if not specified.
3. "experience_level": Map terms to EXACTLY one of these values: "Intern", "Junior", "Mid", "Senior", "Staff", "Principal", "Lead", "Director", "VP". Normalize common synonyms (e.g., "Entry level" -> "Junior", "New grad" -> "Intern", "Sr" -> "Senior"). Set to null if no experience term is present.
4. "role": Clean the query by stripping out all extracted company, location, experience level terms, and filler noise (e.g., "jobs at", "positions in", "looking for", "careers"). Keep only the core job title/discipline.

Output Constraints:
- Respond STRICTLY with raw JSON.
- DO NOT wrap in Markdown fences (no ```json).
- DO NOT add preamble, conversational text, or postscript.

Schema:
{"role": string, "company": string|null, "location": string|null, "experience_level": string|null}

Examples:
Query: "Entry level software jobs at Google in India"
Output: {"role": "Software", "company": "Google", "location": "India", "experience_level": "Junior"}

Query: "Senior Data Scientist hiring remote"
Output: {"role": "Data Scientist", "company": null, "location": "Remote", "experience_level": "Senior"}"""


async def extract_query_filters(query: str) -> dict:
    """Returns {role, company, location, experience_level} — all fields may be None except role."""
    if not query:
        return {"role": "", "company": None, "location": None, "experience_level": None}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    result = await route_call("query_extract", messages, est_tokens=400, max_tokens=200, reasoning_effort="none")

    if result["status"] != "ok":
        return {"role": query, "company": None, "location": None, "experience_level": None}

    try:
        cleaned = re.sub(r"```json|```", "", result["content"]).strip()
        data = json.loads(cleaned)
        return {
            "role": data.get("role") or query,
            "company": data.get("company"),
            "location": data.get("location"),
            "experience_level": data.get("experience_level"),
        }
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"QUERY_EXTRACT PARSE FAILED: {e}, raw content: {result['content'][:300]}")
        return {"role": query, "company": None, "location": None, "experience_level": None}