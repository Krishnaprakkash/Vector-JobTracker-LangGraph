import uuid
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from .config import settings
from .db import get_db, AsyncSessionLocal
from .models import Job, JobStatus, User
from .dedup import compute_job_hash
from .comp_estimator import resolve_compensation
from .scrapers.greenhouse import fetch_greenhouse_jobs
from .scrapers.lever import fetch_lever_jobs
from .scrapers.ashby import fetch_ashby_jobs
from .scrapers.ddgs_fallback import search_jobs_ddgs, relax_query
from .resume_matcher import select_resume_for_query, select_resume_for_job
from .scoring import score_pending_jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

MAX_SLOTS = 150
_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _set_task_status(task_id: str, status: str, detail: dict | None = None):
    r = _get_redis()
    payload = {"status": status, "detail": detail or {}}
    await r.set(f"task:{task_id}", json.dumps(payload), ex=3600)


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse_jobs,
    "lever": fetch_lever_jobs,
    "ashby": fetch_ashby_jobs,
}

# Verified live via seed check — (slug, ats_source)
VERIFIED_COMPANIES = [
    ("stripe", "greenhouse"), ("airbnb", "greenhouse"), ("coinbase", "greenhouse"),
    ("robinhood", "greenhouse"), ("instacart", "greenhouse"), ("asana", "greenhouse"),
    ("databricks", "greenhouse"), ("gitlab", "greenhouse"), ("reddit", "greenhouse"),
    ("roblox", "greenhouse"), ("affirm", "greenhouse"), ("lyft", "greenhouse"),
    ("pinterest", "greenhouse"), ("twilio", "greenhouse"), ("squarespace", "greenhouse"),
    ("peloton", "greenhouse"), ("chime", "greenhouse"), ("brex", "greenhouse"),
    ("gusto", "greenhouse"), ("flexport", "greenhouse"), ("figma", "greenhouse"),
    ("discord", "greenhouse"), ("webflow", "greenhouse"), ("duolingo", "greenhouse"),
    ("spotify", "lever"), ("palantir", "lever"),
    ("openai", "ashby"), ("linear", "ashby"), ("notion", "ashby"), ("ramp", "ashby"),
    ("supabase", "ashby"), ("posthog", "ashby"), ("replit", "ashby"), ("cohere", "ashby"),
    ("zapier", "ashby"), ("render", "ashby"), ("docker", "ashby"), ("benchling", "ashby"),
    ("workos", "ashby"), ("confluent", "ashby"), ("airwallex", "ashby"), ("crusoe", "ashby"),
]


async def _fetch_static_company_jobs(remaining_slots: int) -> list[dict]:
    jobs = []
    for slug, ats in VERIFIED_COMPANIES:
        fetcher = ATS_FETCHERS.get(ats)
        if not fetcher:
            continue
        found = await fetcher(slug)
        for j in found:
            j["source"] = ats
            jobs.append(j)
        if len(jobs) >= remaining_slots:
            break
    return jobs[:remaining_slots]


async def _fetch_general_jobs(role_query: str, needed: int) -> list[dict]:
    jobs = search_jobs_ddgs(role_query, max_results=needed * 2)
    if not jobs:
        relaxed = relax_query(role_query)
        if relaxed != role_query:
            jobs = search_jobs_ddgs(relaxed, max_results=needed * 2)
    return jobs[:needed]


async def _insert_jobs(
    user_id: uuid.UUID,
    db: AsyncSession,
    raw_jobs: list[dict],
    batch_resume_id: uuid.UUID | None,  # set if query provided; None if blank-query (per-job selection)
) -> int:
    inserted = 0
    for j in raw_jobs:
        company = j.get("company") or "unknown"
        title = j.get("title") or ""
        if not title:
            continue

        job_hash = compute_job_hash(company, title)
        exists = await db.execute(
            select(Job.id).where(Job.user_id == user_id, Job.dedup_hash == job_hash)
        )
        if exists.scalar_one_or_none():
            continue

        comp = await resolve_compensation(j)

        resume_id = batch_resume_id
        status = JobStatus.pending_scoring if resume_id else JobStatus.browsing
        if resume_id is None:
            resume_id = await select_resume_for_job(db, user_id, j.get("description", ""))
            if resume_id:
                status = JobStatus.pending_scoring

        db.add(Job(
            user_id=user_id,
            resume_id=resume_id,
            company=company,
            title=title,
            url=j.get("url"),
            description=j.get("description"),
            location=j.get("location"),
            source=j.get("source", "ddgs"),
            dedup_hash=job_hash,
            status=status,
            comp_min=comp.get("comp_min"),
            comp_max=comp.get("comp_max"),
            comp_currency=comp.get("comp_currency"),
            comp_estimated=comp.get("comp_estimated", True),
        ))
        inserted += 1

    await db.commit()
    return inserted


async def _run_refresh(user_id: uuid.UUID, task_id: str, query: str | None):
    async with AsyncSessionLocal() as db:
        try:
            await _set_task_status(task_id, "running")

            result = await db.execute(select(func.count()).select_from(Job).where(
                Job.user_id == user_id, Job.status == JobStatus.browsing
            ))
            current_count = result.scalar_one()
            n_slots = max(0, MAX_SLOTS - current_count)

            if n_slots == 0:
                await _set_task_status(task_id, "done", {"inserted": 0, "reason": "board_full"})
                return

            static_jobs = await _fetch_static_company_jobs(n_slots)
            remaining = n_slots - len(static_jobs)

            general_jobs = []
            if remaining > 0:
                role_query = query or "software engineer"
                general_jobs = await _fetch_general_jobs(role_query, remaining)

            all_jobs = static_jobs + general_jobs

            batch_resume_id = None
            if query:
                batch_resume_id = await select_resume_for_query(db, user_id, query)

            inserted = await _insert_jobs(user_id, db, all_jobs, batch_resume_id)

            score_summary = await score_pending_jobs(db, user_id)

            await _set_task_status(task_id, "done", {
                "inserted": inserted,
                "scored": score_summary["scored"],
                "failed": score_summary["failed"],
            })
        except Exception as e:
            await _set_task_status(task_id, "failed", {"error": str(e)})


@router.post("/refresh")
async def refresh_jobs(user_id: uuid.UUID, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    task_id = str(uuid.uuid4())
    await _set_task_status(task_id, "queued")
    background_tasks.add_task(_run_refresh, user_id, task_id, user.last_search_query)
    return {"task_id": task_id, "status": "queued"}


async def _run_clear(user_id: uuid.UUID, task_id: str, query: str | None):
    async with AsyncSessionLocal() as db:
        try:
            await _set_task_status(task_id, "running")
            await db.execute(
                Job.__table__.delete().where(Job.user_id == user_id, Job.status == JobStatus.browsing)
            )
            await db.commit()
            await _run_refresh(user_id, task_id, query)
        except Exception as e:
            await _set_task_status(task_id, "failed", {"error": str(e)})


@router.post("/clear")
async def clear_jobs(user_id: uuid.UUID, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    task_id = str(uuid.uuid4())
    await _set_task_status(task_id, "queued")
    background_tasks.add_task(_run_clear, user_id, task_id, user.last_search_query)
    return {"task_id": task_id, "status": "queued"}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    r = _get_redis()
    raw = await r.get(f"task:{task_id}")
    if not raw:
        raise HTTPException(404, "Task not found")
    return json.loads(raw)