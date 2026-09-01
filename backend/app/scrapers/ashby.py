import httpx

JOB_BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
TIMEOUT = 10.0


async def fetch_ashby_jobs(slug: str) -> list[dict]:
    url = JOB_BOARD_URL.format(slug=slug)
    params = {"includeCompensation": "true"}

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
        location = job.get("location", "") or job.get("locationName", "")
        comp = job.get("compensation", {}) or {}
        comp_tiers = comp.get("compensationTierSummary")

        jobs.append({
            "title": job.get("title", ""),
            "company": slug,
            "location": location,
            "description": job.get("descriptionPlain", job.get("description", "")),
            "url": job.get("jobUrl", job.get("applyUrl", "")),
            "source": "ashby",
            "comp_min": None,
            "comp_max": None,
            "comp_currency": None,
            "comp_estimated": True,
            "comp_raw_summary": comp_tiers,  # parsed downstream if present
        })
    return jobs