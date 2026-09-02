import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ResumeChunk, Resume
from .embeddings import embed_query


async def _best_resume_for_text(db: AsyncSession, user_id: uuid.UUID, text: str) -> uuid.UUID | None:
    """Returns the resume_id whose best-matching chunk has highest cosine similarity to `text`."""
    if not text:
        return None

    query_vector = embed_query(text)

    # cosine distance via pgvector <=> operator; lower = more similar
    stmt = (
        select(
            ResumeChunk.resume_id,
            func.min(ResumeChunk.embedding.cosine_distance(query_vector)).label("best_distance"),
        )
        .join(Resume, Resume.id == ResumeChunk.resume_id)
        .where(Resume.user_id == user_id)
        .group_by(ResumeChunk.resume_id)
        .order_by("best_distance")
        .limit(1)
    )

    result = await db.execute(stmt)
    row = result.first()
    return row.resume_id if row else None


async def select_resume_for_query(db: AsyncSession, user_id: uuid.UUID, query: str) -> uuid.UUID | None:
    """Query-provided path: one resume for the whole batch, matched against the search query."""
    return await _best_resume_for_text(db, user_id, query)


async def select_resume_for_job(db: AsyncSession, user_id: uuid.UUID, job_description: str) -> uuid.UUID | None:
    """Blank-query path: per-job resume selection, matched against the job description."""
    return await _best_resume_for_text(db, user_id, job_description or "")