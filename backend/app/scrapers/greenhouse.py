import httpx

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
TIMEOUT = 10.0


async def fetch_greenhouse_jobs(slug: str) -> list[dict]:
    url = BASE_URL.format(slug=slug)
    params = {"content": "true"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
    except httpx.TimeoutException:
        return []

    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    jobs = []
    for job in data.get("jobs", []):
        location = job.get("location", {}).get("name", "")
        jobs.append({
            "title": job.get("title", ""),
            "company": slug,
            "location": location,
            "description": job.get("content", ""),
            "url": job.get("absolute_url", ""),
            "source": "greenhouse",
        })
    return jobs