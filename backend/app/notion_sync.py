import asyncio

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from .models import Job, User
from .fit import fit_label
from .notion_rate_limiter import throttle_notion

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
MAX_RETRIES = 2


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _job_properties(job: Job) -> dict:
    props = {
        "Title": {"title": [{"text": {"content": job.title[:2000]}}]},
        "Company": {"rich_text": [{"text": {"content": job.company[:2000]}}]},
        "Status": {"select": {"name": job.status.value}},
    }
    if job.location:
        props["Location"] = {"rich_text": [{"text": {"content": job.location[:2000]}}]}
    if job.comp_min is not None:
        props["Comp Min"] = {"number": job.comp_min}
    if job.comp_max is not None:
        props["Comp Max"] = {"number": job.comp_max}
    if job.comp_currency:
        props["Comp Currency"] = {"select": {"name": job.comp_currency}}
    if job.match_score is not None:
        props["Match Score"] = {"number": job.match_score}
        label = fit_label(job.match_score)
        if label:
            props["Fit"] = {"select": {"name": label}}
    if job.match_rationale:
        props["Match Rationale"] = {"rich_text": [{"text": {"content": job.match_rationale[:2000]}}]}
    if job.source:
        props["Source"] = {"select": {"name": job.source}}
    if job.url:
        props["URL"] = {"url": job.url}
    return props


def _description_body(job: Job) -> list[dict]:
    if not job.description:
        return []
    text = job.description[:2000]
    return [{
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }]


async def _request_with_retry(client: httpx.AsyncClient, method: str, url: str, headers: dict, json_body: dict, workspace_id: str) -> httpx.Response:
    for attempt in range(MAX_RETRIES + 1):
        await throttle_notion(workspace_id)
        resp = await client.request(method, url, headers=headers, json=json_body)
        if resp.status_code != 429:
            return resp
        retry_after = float(resp.headers.get("Retry-After", "1"))
        if attempt < MAX_RETRIES:
            await asyncio.sleep(retry_after)
    return resp  # exhausted retries; caller checks status


async def sync_job_to_notion(db: AsyncSession, job: Job, user: User) -> bool:
    """Returns True on success, False on failure. Never raises — per-job Notion
    sync failures are an accepted gap (consistent with comp/scoring_failed pattern)
    and must not abort the calling batch."""
    if not user.notion_access_token or not user.notion_jobs_data_source_id:
        return False

    headers = _headers(user.notion_access_token)
    properties = _job_properties(job)
    workspace_id = user.notion_workspace_id or str(user.id)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if job.notion_page_id:
                resp = await _request_with_retry(
                    client, "PATCH", f"{NOTION_API}/pages/{job.notion_page_id}",
                    headers, {"properties": properties}, workspace_id,
                )
                if resp.status_code == 404:
                    job.notion_page_id = None
                elif resp.status_code >= 400:
                    return False
                else:
                    return True

            payload = {
                "parent": {"type": "data_source_id", "data_source_id": user.notion_jobs_data_source_id},
                "properties": properties,
                "children": _description_body(job),
            }
            resp = await _request_with_retry(
                client, "POST", f"{NOTION_API}/pages", headers, payload, workspace_id,
            )
            if resp.status_code >= 400:
                return False

            job.notion_page_id = resp.json()["id"]
            await db.commit()
            return True
    except Exception:
        return False