import uuid
import json
import re
import httpx
import numpy as np
import redis.asyncio as aioredis

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict

from .config import settings
from .db import get_db, AsyncSessionLocal
from .models import Job, JobStatus, User, Resume
from .dedup import compute_job_hash
from .comp_estimator import resolve_compensation
from .scrapers.greenhouse import fetch_greenhouse_jobs
from .scrapers.lever import fetch_lever_jobs
from .scrapers.ashby import fetch_ashby_jobs
from .scrapers.smartrecruiters import fetch_smartrecruiters_jobs
from .scrapers.recruitee import fetch_recruitee_jobs
from .scrapers.workable import fetch_workable_jobs
from .resume_matcher import select_resume_for_query, select_resume_for_job
from .scoring import score_pending_jobs
from .embeddings import embed_query, embed_texts
from .location_filter import location_matches_strict
from .query_extract import extract_query_filters
from .seniority import detect_seniority


router = APIRouter(prefix="/api/jobs", tags=["jobs"])

MAX_SLOTS = 70
MAX_JOBS_PER_COMPANY = 5
_redis: aioredis.Redis | None = None

TRACKER_STATUSES = [JobStatus.saved, JobStatus.applied, JobStatus.interviewing, JobStatus.negotiating]


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis

def _cosine_sim(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


async def _set_task_status(task_id: str, status: str, detail: dict | None = None):
    r = _get_redis()
    payload = {"status": status, "detail": detail or {}}
    await r.set(f"task:{task_id}", json.dumps(payload), ex=3600)


ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse_jobs,
    "lever": fetch_lever_jobs,
    "ashby": fetch_ashby_jobs,
    "smartrecruiters": fetch_smartrecruiters_jobs,
    "recruitee": fetch_recruitee_jobs,
    "workable": fetch_workable_jobs,
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

_COMPANIES_BY_ATS = defaultdict(list)
for slug, ats in VERIFIED_COMPANIES:
    _COMPANIES_BY_ATS[ats].append(slug)


async def _fetch_static_company_jobs(
    remaining_slots: int, query: str | None, home_location: str | None,
    company_filter: str | None, experience_level: str | None,
) -> list[dict]:
    if company_filter:
        matches = [(slug, ats) for slug, ats in VERIFIED_COMPANIES if company_filter.lower() in slug.lower()]
        if not matches:
            return []
        jobs = []
        for slug, ats in matches:
            fetcher = ATS_FETCHERS.get(ats)
            if not fetcher:
                continue
            found = await fetcher(slug)
            print(f"FETCHED {len(found)} from {slug} ({ats})")
            if home_location:
                found = [j for j in found if location_matches_strict(j.get("location"), home_location)]
            if experience_level:
                found = [j for j in found if detect_seniority(j.get("title", ""), j.get("description", "")) == experience_level]
            for j in found:
                j["source"] = ats
            jobs.extend(found)
        return jobs[:remaining_slots]

    ats_list = list(_COMPANIES_BY_ATS.keys())
    per_ats_target = remaining_slots // len(ats_list) if ats_list else 0

    jobs = []
    for ats in ats_list:
        fetcher = ATS_FETCHERS.get(ats)
        if not fetcher:
            continue
        ats_jobs = []
        for slug in _COMPANIES_BY_ATS[ats]:
            found = await fetcher(slug)
            if home_location:
                found = [j for j in found if location_matches_strict(j.get("location"), home_location)]
            if experience_level:
                found = [j for j in found if detect_seniority(j.get("title", ""), j.get("description", "")) == experience_level]
            capped = found[:MAX_JOBS_PER_COMPANY]
            for j in capped:
                j["source"] = ats
            ats_jobs.extend(capped)
            if len(ats_jobs) >= per_ats_target * 3:
                break
        jobs.extend(ats_jobs)

    if not query or not jobs:
        return jobs[:remaining_slots]

    query_vector = embed_query(query)
    titles = [j["title"] for j in jobs]
    title_vectors = embed_texts(titles)
    scored = [(j, _cosine_sim(query_vector, tv)) for j, tv in zip(jobs, title_vectors)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [j for j, _ in scored[:remaining_slots]]

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

            user = await db.get(User, user_id)
            home_location = user.home_location if user else None

            filters = await extract_query_filters(query) if query else {"role": query, "company": None, "experience_level": None}
            role_query_text = filters["role"]
            company_filter = filters["company"]
            experience_level = filters["experience_level"]

            all_jobs = await _fetch_static_company_jobs(n_slots, role_query_text, home_location, company_filter, experience_level)

            batch_resume_id = None
            if role_query_text:
                batch_resume_id = await select_resume_for_query(db, user_id, role_query_text)

            inserted = await _insert_jobs(user_id, db, all_jobs, batch_resume_id)

            score_summary = await score_pending_jobs(db, user_id)

            await _set_task_status(task_id, "done", {
                "inserted": inserted,
                "scored": score_summary["scored"],
                "failed": score_summary["failed"],
            })
        except Exception as e:
            await _set_task_status(task_id, "failed", {"error": str(e)})


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

@router.patch("/{job_id}/status")
async def update_job_status(job_id: uuid.UUID, user_id: uuid.UUID, status: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(404, "Job not found")

    try:
        new_status = JobStatus(status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {status}")

    job.status = new_status
    await db.commit()
    return {"id": job.id, "status": job.status.value}


@router.delete("/{job_id}")
async def delete_job(job_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(404, "Job not found")
    await db.delete(job)
    await db.commit()
    return {"status": "deleted"}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    r = _get_redis()
    raw = await r.get(f"task:{task_id}")
    if not raw:
        raise HTTPException(404, "Task not found")
    return json.loads(raw)

@router.get("")
async def list_jobs(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job).where(Job.user_id == user_id, Job.status == JobStatus.browsing).order_by(Job.created_at)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "company": j.company,
            "title": j.title,
            "url": j.url,
            "location": j.location,
            "source": j.source,
            "match_score": j.match_score,
            "match_rationale": j.match_rationale,
            "comp_min": j.comp_min,
            "comp_max": j.comp_max,
            "comp_currency": j.comp_currency,
            "comp_estimated": j.comp_estimated,
            "status": j.status.value,
        }
        for j in jobs
    ]

def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _resolve_description(raw_input: str) -> str:
    if raw_input.strip().startswith(("http://", "https://")):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(raw_input.strip())
            resp.raise_for_status()
            return _strip_html(resp.text)[:5000]
        except Exception:
            return ""  # best-effort — failed fetch just means empty description, not a hard error
    return raw_input.strip()[:5000]


@router.post("/manual")
async def add_manual_job(
    user_id: uuid.UUID,
    company: str,
    title: str,
    location: str,
    resume_id: uuid.UUID,
    raw_input: str,  # URL or pasted text
    comp_min: int | None = None,
    comp_max: int | None = None,
    comp_currency: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume or resume.user_id != user_id:
        raise HTTPException(404, "Resume not found")

    description = await _resolve_description(raw_input)
    dedup_key = f"manual-{uuid.uuid4()}"  # exempted from real dedup, but column is NOT NULL so needs a value

    job = Job(
        user_id=user_id,
        resume_id=resume_id,
        company=company.strip(),
        title=title.strip(),
        location=location.strip() or None,
        url=raw_input.strip() if raw_input.strip().startswith(("http://", "https://")) else None,
        description=description or None,
        source="manual",
        dedup_hash=dedup_key,
        status=JobStatus.applied,
        comp_min=comp_min,
        comp_max=comp_max,
        comp_currency=comp_currency,
        comp_estimated=False,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return {"id": job.id, "company": job.company, "title": job.title, "status": job.status.value}

@router.get("/tracked")
async def list_tracked_jobs(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job).where(Job.user_id == user_id, Job.status.in_(TRACKER_STATUSES)).order_by(Job.updated_at.desc())
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id, "company": j.company, "title": j.title, "url": j.url,
            "location": j.location, "status": j.status.value,
            "comp_min": j.comp_min, "comp_max": j.comp_max, "comp_currency": j.comp_currency,
        }
        for j in jobs
    ]