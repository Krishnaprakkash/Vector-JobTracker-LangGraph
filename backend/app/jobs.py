# backend/app/jobs.py
import uuid
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from .config import settings
from .db import get_db, AsyncSessionLocal
from .models import Job, JobStatus, PinnedCompany, User
from .dedup import compute_job_hash
from .comp_estimator import resolve_compensation
from .scrapers.greenhouse import fetch_greenhouse_jobs
from .scrapers.lever import fetch_lever_jobs
from .scrapers.ashby import fetch_ashby_jobs
from .scrapers.ddgs_fallback import search_jobs_ddgs, relax_query

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

MAX_SLOTS = 50
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


async def _fetch_pinned_jobs(user_id: uuid.UUID, db: AsyncSession, remaining_slots: int) -> list[dict]:
    result = await db.execute(select(PinnedCompany).where(PinnedCompany.user_id == user_id))
    pinned = result.scalars().all()

    jobs = []
    for p in pinned:
        fetcher = ATS_FETCHERS.get(p.ats_source)
        if not fetcher:
            continue
        found = await fetcher(p.company_slug)
        for j in found:
            j["source"] = p.ats_source
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


async def _insert_jobs(user_id: uuid.UUID, db: AsyncSession, raw_jobs: list[dict]) -> int:
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

        db.add(Job(
            user_id=user_id,
            company=company,
            title=title,
            url=j.get("url"),
            description=j.get("description"),
            location=j.get("location"),
            source=j.get("source", "ddgs"),
            dedup_hash=job_hash,
            status=JobStatus.browsing,
            comp_min=comp.get("comp_min"),
            comp_max=comp.get("comp_max"),
            comp_currency=comp.get("comp_currency"),
            comp_estimated=comp.get("comp_estimated", True),
        ))
        inserted += 1

    await db.commit()
    return inserted


async def _select_resume_for_batch(user: User, query: str | None) -> uuid.UUID | None:
    if not user.resumes:
        return None
    if query:
        # single resume for whole batch — real matching logic lands in Phase 4
        return user.resumes[0].id
    return None  # blank query: per-job resume selection happens in Phase 4 scoring step


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

            pinned_jobs = await _fetch_pinned_jobs(user_id, db, n_slots)
            remaining = n_slots - len(pinned_jobs)

            general_jobs = []
            if remaining > 0:
                role_query = query or "software engineer"
                general_jobs = await _fetch_general_jobs(role_query, remaining)

            all_jobs = pinned_jobs + general_jobs
            inserted = await _insert_jobs(user_id, db, all_jobs)

            user = await db.get(User, user_id)
            resume_id = await _select_resume_for_batch(user, query)
            if resume_id:
                await db.execute(
                    Job.__table__.update()
                    .where(Job.user_id == user_id, Job.status == JobStatus.browsing, Job.resume_id.is_(None))
                    .values(resume_id=resume_id, status=JobStatus.pending_scoring)
                )
                await db.commit()

            await _set_task_status(task_id, "done", {"inserted": inserted})
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