import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .auth import get_current_user
from .models import User

router = APIRouter(prefix="/api/notion", tags=["notion"])

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

JOB_STATUS_OPTIONS = [
    "browsing", "pending_scoring", "saved", "applied",
    "interviewing", "negotiating", "scoring_failed",
]


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def _find_parent_page(token: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{NOTION_API}/search",
            headers=_headers(token),
            json={"filter": {"property": "object", "value": "page"}},
        )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise HTTPException(400, "No shared page found. Share a page with the VECTOR integration first.")

    for page in results:
        title_prop = page.get("properties", {}).get("title", {})
        texts = title_prop.get("title", []) if isinstance(title_prop, dict) else []
        title = "".join(t.get("plain_text", "") for t in texts)
        if title.strip().lower() == "vector":
            return page["id"]

    return results[0]["id"]


async def _create_database(token: str, parent_page_id: str, title: str, properties: dict) -> str:
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{NOTION_API}/databases", headers=_headers(token), json=payload)
    if resp.status_code != 200:
        raise HTTPException(502, f"Notion database creation failed ({title}): {resp.text}")
    return resp.json()["id"]


def _jobs_db_properties(resumes_db_id: str) -> dict:
    return {
        "Title": {"title": {}},
        "Company": {"rich_text": {}},
        "Location": {"rich_text": {}},
        "Comp Min": {"number": {}},
        "Comp Max": {"number": {}},
        "Comp Currency": {"select": {"options": [{"name": c} for c in ["USD", "EUR", "GBP", "INR"]]}},
        "Match Score": {"number": {}},
        "Match Rationale": {"rich_text": {}},
        "Fit": {"select": {"options": [{"name": f} for f in ["Reasonable", "Moderate", "Aspirational"]]}},
        "Source": {"select": {"options": [
            {"name": s} for s in ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable", "manual"]
        ]}},
        "URL": {"url": {}},
        "Status": {"select": {"options": [{"name": s} for s in JOB_STATUS_OPTIONS]}},
        "Resume": {"relation": {"database_id": resumes_db_id, "single_property": {}}},
    }


def _resumes_db_properties() -> dict:
    return {
        "Name": {"title": {}},
        "File": {"files": {}},
        "Resume ID": {"rich_text": {}},
    }


def _settings_db_properties() -> dict:
    return {
        "Name": {"title": {}},
        "Refresh Trigger": {"checkbox": {}},
        "Status Message": {"rich_text": {}},
        "Search Query": {"rich_text": {}},
    }


async def run_notion_setup(user: User, db: AsyncSession) -> dict:
    if user.notion_jobs_db_id:
        return {
            "status": "already_set_up",
            "jobs_db_id": user.notion_jobs_db_id,
            "resumes_db_id": user.notion_resumes_db_id,
            "settings_db_id": user.notion_settings_db_id,
        }

    token = user.notion_access_token
    parent_page_id = await _find_parent_page(token)

    resumes_db_id = await _create_database(token, parent_page_id, "Resumes", _resumes_db_properties())
    jobs_db_id = await _create_database(token, parent_page_id, "Jobs", _jobs_db_properties(resumes_db_id))
    settings_db_id = await _create_database(token, parent_page_id, "Settings", _settings_db_properties())

    user.notion_jobs_db_id = jobs_db_id
    user.notion_resumes_db_id = resumes_db_id
    user.notion_settings_db_id = settings_db_id
    await db.commit()

    return {
        "status": "created",
        "jobs_db_id": jobs_db_id,
        "resumes_db_id": resumes_db_id,
        "settings_db_id": settings_db_id,
    }


@router.post("/setup")
async def notion_setup(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.notion_access_token:
        raise HTTPException(400, "Notion not connected for this user")
    return await run_notion_setup(user, db)