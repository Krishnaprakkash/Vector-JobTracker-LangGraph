import httpx

BASE_URL = "https://api.lever.co/v0/postings/{slug}"
TIMEOUT = 10.0


async def fetch_lever_jobs(slug: str) -> list[dict]:
    url = BASE_URL.format(slug=slug)
    params = {"mode": "json"}

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
    for job in data:
        categories = job.get("categories", {})
        jobs.append({
            "title": job.get("text", ""),
            "company": slug,
            "location": categories.get("location", ""),
            "description": job.get("descriptionPlain", job.get("description", "")),
            "url": job.get("hostedUrl", ""),
            "source": "lever",
        })
    return jobs