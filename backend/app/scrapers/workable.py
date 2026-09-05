import httpx

BASE_URL = "https://apply.workable.com/api/v1/widget/accounts/{client_name}"
TIMEOUT = 10.0


async def fetch_workable_jobs(client_name: str) -> list[dict]:
    url = BASE_URL.format(client_name=client_name)

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
    for job in data.get("jobs", []):
        jobs.append({
            "title": job.get("title", ""),
            "company": client_name,
            "location": job.get("location", {}).get("city", "") if isinstance(job.get("location"), dict) else "",
            "description": job.get("description", ""),
            "url": job.get("url", ""),
            "source": "workable",
        })
    return jobs