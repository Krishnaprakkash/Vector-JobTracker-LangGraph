import httpx

BASE_URL = "https://{company}.recruitee.com/api/offers/"
TIMEOUT = 10.0


async def fetch_recruitee_jobs(company: str) -> list[dict]:
    url = BASE_URL.format(company=company)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return []

    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    jobs = []
    for job in data.get("offers", []):
        jobs.append({
            "title": job.get("title", ""),
            "company": company,
            "location": job.get("city", "") or job.get("country", ""),
            "description": job.get("description", ""),
            "url": job.get("careers_url", ""),
            "source": "recruitee",
        })
    return jobs