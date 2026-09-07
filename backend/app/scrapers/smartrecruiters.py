import httpx

BASE_URL = "https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
TIMEOUT = 10.0


async def fetch_smartrecruiters_jobs(company_id: str) -> list[dict]:
    url = BASE_URL.format(company_id=company_id)

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
    for job in data.get("content", []):
        location = job.get("location", {}).get("city", "") or job.get("location", {}).get("country", "")
        jobs.append({
            "title": job.get("name", ""),
            "company": company_id,
            "location": location,
            "description": job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
            "url": job.get("applyUrl", job.get("ref", "")),
            "source": "smartrecruiters",
        })
    return jobs