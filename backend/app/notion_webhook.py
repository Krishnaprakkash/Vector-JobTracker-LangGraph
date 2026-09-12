import hashlib
import hmac
import uuid
import asyncio
import os

import httpx
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from sqlalchemy import select, func

from .config import settings
from .db import AsyncSessionLocal
from .models import Job, User, Resume, JobStatus, ResumeChunk
from .resumes import _resume_path, _build_summary
from .resume_parser import extract_resume_text
from .chunking import chunk_resume_text
from .embeddings import embed_texts
from .manual_add import extract_jsonld_jobposting, enrich_manual_job, tavily_search_summarize

router = APIRouter(prefix="/api/notion-webhook", tags=["notion"])

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.notion_webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def _extract_title_text(prop: dict | None) -> str:
    if not prop:
        return ""
    return "".join(t.get("plain_text", "") for t in prop.get("title", []))


def _extract_rich_text(prop: dict | None) -> str:
    if not prop:
        return ""
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))


async def _resolve_resume_id(db, user_id, resume_notion_page_id: str | None):
    if not resume_notion_page_id:
        return None
    result = await db.execute(
        select(Resume.id).where(Resume.notion_page_id == resume_notion_page_id, Resume.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def _sync_enriched_fields_to_notion(token: str, page_id: str, location: str | None, description: str | None, enrichment: dict, status: str | None = None, source: str | None = None) -> None:
    from .fit import fit_label

    properties = {}
    if location:
        properties["Location"] = {"rich_text": [{"text": {"content": location[:2000]}}]}
    if enrichment.get("comp_min") is not None:
        properties["Comp Min"] = {"number": enrichment["comp_min"]}
    if enrichment.get("comp_max") is not None:
        properties["Comp Max"] = {"number": enrichment["comp_max"]}
    if enrichment.get("comp_currency"):
        properties["Comp Currency"] = {"select": {"name": enrichment["comp_currency"]}}
    if enrichment.get("match_score") is not None:
        properties["Match Score"] = {"number": enrichment["match_score"]}
        label = fit_label(enrichment["match_score"])
        if label:
            properties["Fit"] = {"select": {"name": label}}
    if enrichment.get("match_rationale"):
        properties["Match Rationale"] = {"rich_text": [{"text": {"content": enrichment["match_rationale"][:2000]}}]}
    if status:
        properties["Status"] = {"select": {"name": status}}
    if source:
        properties["Source"] = {"select": {"name": source}}

    if not properties:
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"properties": properties},
        )

async def _handle_job_created(user: User, page: dict) -> None:
    props = page.get("properties", {})
    title = _extract_title_text(props.get("Title"))
    company = _extract_rich_text(props.get("Company"))
    url_prop = props.get("URL", {}).get("url")
    resume_relation = props.get("Resume", {}).get("relation", [])
    resume_page_id = resume_relation[0]["id"] if resume_relation else None

    if not title:
        return  # nothing usable yet; user still typing

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Job.id).where(Job.notion_page_id == page["id"]))
        if existing.scalar_one_or_none():
            return  # page created via our own API sync, not a genuine user-created row

        resume_id = await _resolve_resume_id(db, user.id, resume_page_id)
        if resume_page_id and not resume_id:
            await asyncio.sleep(3)
            resume_id = await _resolve_resume_id(db, user.id, resume_page_id)

        description = None
        location = None
        if url_prop:
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.get(url_prop)
                resp.raise_for_status()
                parsed = extract_jsonld_jobposting(resp.text)
            except Exception:
                parsed = None
            if parsed:
                title = title or parsed.get("title") or title
                company = company or parsed.get("company") or company
                location = parsed.get("location")
                description = parsed.get("description")

        if not description:
            description = await tavily_search_summarize(title, company, None)

        enrichment = await enrich_manual_job(db, title, location, description, resume_id, None, None)

        dedup_key = f"notion-{page['id']}"
        job = Job(
            user_id=user.id,
            resume_id=resume_id,
            company=company or "unknown",
            title=title,
            location=location,
            url=url_prop,
            description=description or None,
            source="manual",
            dedup_hash=dedup_key,
            status=JobStatus.applied,
            notion_page_id=page["id"],
            comp_min=enrichment.get("comp_min"),
            comp_max=enrichment.get("comp_max"),
            comp_currency=enrichment.get("comp_currency"),
            comp_estimated=enrichment.get("comp_estimated", False),
            match_score=enrichment.get("match_score"),
            match_rationale=enrichment.get("match_rationale"),
        )
        db.add(job)
        await db.commit()

    await _sync_enriched_fields_to_notion(user.notion_access_token, page["id"], location, description, enrichment, status=job.status.value, source=job.source)


async def _handle_resume_created(user: User, page: dict) -> None:
    props = page.get("properties", {})
    files = props.get("File", {}).get("files", [])

    if not files:
        await asyncio.sleep(3)
        page = await _fetch_page(user.notion_access_token, page["id"])
        files = page.get("properties", {}).get("File", {}).get("files", [])

    if not files:
        return  # accepted gap: no file attached

    file_info = files[0]
    file_url = (file_info.get("file") or file_info.get("external") or {}).get("url")
    filename = file_info.get("name", "resume.pdf")

    if not file_url or not filename.lower().endswith(".pdf"):
        return

    resume_id = uuid.uuid4()
    file_path = _resume_path(resume_id)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(file_url)
    resp.raise_for_status()

    with open(file_path, "wb") as f:
        f.write(resp.content)

    async with AsyncSessionLocal() as db:
        try:
            text = extract_resume_text(file_path)
            if not text:
                return
            chunks = chunk_resume_text(text)
            if not chunks:
                return
            embeddings = embed_texts([c["content"] for c in chunks])
            summary = _build_summary(chunks)

            resume = Resume(id=resume_id, user_id=user.id, filename=filename, summary=summary, notion_page_id=page["id"])
            db.add(resume)
            await db.flush()

            for chunk, vector in zip(chunks, embeddings):
                db.add(ResumeChunk(resume_id=resume.id, section=chunk["section"], content=chunk["content"], embedding=vector))

            await db.commit()
        except Exception:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise


async def _fetch_page(token: str, page_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{NOTION_API}/pages/{page_id}", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


async def _reset_checkbox(token: str, page_id: str, prop_name: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"properties": {prop_name: {"checkbox": False}}},
        )


async def _write_status_message(token: str, page_id: str, message: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"properties": {"Status Message": {"rich_text": [{"text": {"content": message}}]}}},
        )


async def _handle_settings_change(user: User, page: dict, background_tasks: BackgroundTasks) -> None:
    from .jobs import _run_refresh, _set_task_status

    trigger = page.get("properties", {}).get("Refresh Trigger", {}).get("checkbox")
    if not trigger:
        return

    search_query = _extract_rich_text(page.get("properties", {}).get("Search Query")).strip() or None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(Resume).where(Resume.user_id == user.id))
        resume_count = result.scalar_one()

        db_user = await db.get(User, user.id)
        db_user.last_search_query = search_query
        await db.commit()

    if resume_count == 0:
        await _write_status_message(user.notion_access_token, page["id"], "⚠️ Upload a resume first")
        await _reset_checkbox(user.notion_access_token, page["id"], "Refresh Trigger")
        return

    await _write_status_message(user.notion_access_token, page["id"], "")
    task_id = str(uuid.uuid4())
    await _set_task_status(task_id, "queued")
    background_tasks.add_task(_run_refresh, user.id, task_id, search_query)
    await _reset_checkbox(user.notion_access_token, page["id"], "Refresh Trigger")


async def _handle_job_status_change(user: User, page: dict) -> None:
    status_name = page.get("properties", {}).get("Status", {}).get("select", {})
    status_name = status_name.get("name") if status_name else None
    if not status_name:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.notion_page_id == page["id"], Job.user_id == user.id))
        job = result.scalar_one_or_none()
        if job and job.status.value != status_name:
            try:
                job.status = job.status.__class__(status_name)
                await db.commit()
            except ValueError:
                pass  # unrecognized status value typed into Notion; accepted gap


@router.post("")
async def notion_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    payload = await request.json()

    if "verification_token" in payload:
        print(f"NOTION WEBHOOK VERIFICATION TOKEN: {payload['verification_token']}")
        return {"status": "received"}

    if not _verify_signature(raw_body, request.headers.get("X-Notion-Signature")):
        raise HTTPException(401, "Invalid signature")

    event_type = payload.get("type")
    if event_type not in ("page.created", "page.properties_updated", "page.deleted"):
        return {"status": "ignored"}

    workspace_id = payload.get("workspace_id")
    entity = payload.get("entity", {})
    entity_id = entity.get("id")
    if not workspace_id or not entity_id or entity.get("type") != "page":
        return {"status": "ignored"}

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.notion_workspace_id == workspace_id))
        user = result.scalar_one_or_none()

    if not user or not user.notion_access_token:
        return {"status": "ignored"}

    try:
        if event_type == "page.deleted":
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Job).where(Job.notion_page_id == entity_id, Job.user_id == user.id))
                job = result.scalar_one_or_none()
                if job:
                    await db.delete(job)
                    await db.commit()
            return {"status": "ok"}
        page = await _fetch_page(user.notion_access_token, entity_id)
    except Exception:
        return {"status": "fetch_failed"}

    parent = page.get("parent", {})
    parent_db_id = parent.get("database_id")

    if parent_db_id == user.notion_settings_db_id:
        await _handle_settings_change(user, page, background_tasks)
    elif parent_db_id == user.notion_jobs_db_id:
        if event_type == "page.created":
            background_tasks.add_task(_handle_job_created, user, page)
        else:
            await _handle_job_status_change(user, page)
    elif parent_db_id == user.notion_resumes_db_id:
        if event_type == "page.created":
            background_tasks.add_task(_handle_resume_created, user, page)
    return {"status": "ok"}