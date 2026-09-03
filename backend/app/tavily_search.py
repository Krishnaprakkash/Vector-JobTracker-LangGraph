import httpx
from .config import settings

TAVILY_URL = "https://api.tavily.com/search"


async def tavily_search(query: str, max_results: int = 3) -> str:
    payload = {"api_key": settings.tavily_api_key, "query": query, "max_results": max_results}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(TAVILY_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return "\n".join(f"- {r.get('title', '')}: {r.get('content', '')[:300]}" for r in results)
    except Exception:
        return ""

async def tavily_search_cover_letter(query: str, max_results: int = 3) -> str:
    payload = {"api_key": settings.tavily_cover_letter_api_key, "query": query, "max_results": max_results}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(TAVILY_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return "\n".join(f"- {r.get('title', '')}: {r.get('content', '')[:300]}" for r in results)
    except Exception:
        return ""