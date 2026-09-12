import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Job, JobStatus, Profile, ProfileChunk
from .rate_limiter import route_call
from .embeddings import embed_query

EXTRACT_SYSTEM_PROMPT = (
    "You are a job description parser. Extract structured requirements from the job description. "
    "Respond ONLY with JSON: {\"required_skills\": [str], \"years_experience\": int|null, "
    "\"key_responsibilities\": [str]}. No prose, no markdown fences."
)

SCORE_SYSTEM_PROMPT = (
    "You are a resume-to-job fit evaluator. Given a job's requirements and relevant resume excerpts, "
    "score how well the candidate fits on a 0-100 scale and explain why in 2-3 sentences. "
    "Respond ONLY with JSON: {\"match_score\": float, \"match_rationale\": str}. No prose, no markdown fences."
)

TOP_K_CHUNKS = 5


def _strip_json_fences(text: str) -> str:
    return re.sub(r"```json|```", "", text).strip()


async def extract_job_requirements(description: str) -> dict | None:
    if not description:
        return None

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": description[:4000]},  # cap input length
    ]
    result = await route_call("extract", messages, est_tokens=800, max_tokens=500)
    if result["status"] != "ok":
        return None

    try:
        data = json.loads(_strip_json_fences(result["content"]))
        return data
    except json.JSONDecodeError:
        return None


async def _get_top_profile_chunks(db: AsyncSession, user_id: uuid.UUID, job_description: str) -> list[str]:
    if not job_description:
        return []
    query_vector = embed_query(job_description)

    stmt = (
        select(ProfileChunk.content)
        .join(Profile, Profile.id == ProfileChunk.profile_id)
        .where(Profile.user_id == user_id)
        .order_by(ProfileChunk.embedding.cosine_distance(query_vector))
        .limit(TOP_K_CHUNKS)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def score_job_fit(
    job_title: str,
    job_description: str,
    extracted: dict | None,
    profile_chunks: list[str],
) -> dict | None:
    requirements_text = json.dumps(extracted)[:1500] if extracted else "Not available"
    profile_text = "\n---\n".join(c[:800] for c in profile_chunks) if profile_chunks else "No profile excerpts available"

    prompt = (
        f"Job Title: {job_title}\n"
        f"Job Description: {job_description[:2000]}\n\n"
        f"Extracted Requirements: {requirements_text}\n\n"
        f"Relevant Profile Excerpts:\n{profile_text}"
    )
    messages = [
        {"role": "system", "content": SCORE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    result = await route_call("score_reason", messages, est_tokens=800, max_tokens=300)
    if result["status"] != "ok":
        return None

    try:
        data = json.loads(_strip_json_fences(result["content"]))
        if "match_score" in data and "match_rationale" in data:
            return {
                "match_score": float(data["match_score"]),
                "match_rationale": str(data["match_rationale"]),
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    return None


async def score_pending_jobs(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Processes all pending_scoring jobs for a user. Returns summary counts."""
    result = await db.execute(
        select(Job).where(Job.user_id == user_id, Job.status == JobStatus.pending_scoring)
    )
    jobs = result.scalars().all()

    scored = 0
    failed = 0

    for job in jobs:
        profile_chunks = await _get_top_profile_chunks(db, user_id, job.description or "")

        if not profile_chunks:
            job.status = JobStatus.scoring_failed
            failed += 1
            continue

        extracted = await extract_job_requirements(job.description or "")
        score_result = await score_job_fit(job.title, job.description or "", extracted, profile_chunks)

        if score_result is None:
            job.status = JobStatus.scoring_failed
            failed += 1
            continue

        job.match_score = score_result["match_score"]
        job.match_rationale = score_result["match_rationale"]
        job.status = JobStatus.browsing
        scored += 1

    await db.commit()
    return {"scored": scored, "failed": failed}