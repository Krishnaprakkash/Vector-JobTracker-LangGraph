import os
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .auth import get_current_user
from .models import Resume, ResumeChunk, User
from .resume_parser import extract_resume_text
from .chunking import chunk_resume_text
from .embeddings import embed_texts

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

MAX_SUMMARY_CHARS = 1000
RESUME_DIR = os.path.join(settings.STORAGE_DIR, "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)


def _resume_path(resume_id: uuid.UUID) -> str:
    return os.path.join(RESUME_DIR, f"{resume_id}.pdf")


def _build_summary(chunks: list[dict]) -> str | None:
    skills_content = " ".join(c["content"] for c in chunks if c["section"] == "skills")
    if not skills_content:
        return None
    return skills_content[:MAX_SUMMARY_CHARS].strip()


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files accepted")

    resume_id = uuid.uuid4()
    file_path = _resume_path(resume_id)
    content_bytes = await file.read()

    with open(file_path, "wb") as f:
        f.write(content_bytes)

    try:
        text = extract_resume_text(file_path)
        if not text:
            raise HTTPException(422, "Could not extract text from PDF")

        chunks = chunk_resume_text(text)
        if not chunks:
            raise HTTPException(422, "No content chunks found")

        embeddings = embed_texts([c["content"] for c in chunks])
        summary = _build_summary(chunks)

        resume = Resume(id=resume_id, user_id=user.id, filename=file.filename, summary=summary)
        db.add(resume)
        await db.flush()

        for chunk, vector in zip(chunks, embeddings):
            db.add(ResumeChunk(
                resume_id=resume.id,
                section=chunk["section"],
                content=chunk["content"],
                embedding=vector,
            ))

        await db.commit()
        await db.refresh(resume)
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    return {"resume_id": resume.id, "filename": resume.filename, "chunk_count": len(chunks)}


@router.get("/{resume_id}/file")
async def get_resume_file(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    resume = await db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise HTTPException(404, "Resume not found")
    path = _resume_path(resume_id)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path, media_type="application/pdf", filename=resume.filename)


@router.delete("/{resume_id}")
async def delete_resume(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    resume = await db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise HTTPException(404, "Resume not found")
    await db.delete(resume)
    await db.commit()
    path = _resume_path(resume_id)
    if os.path.exists(path):
        os.remove(path)
    return {"status": "deleted"}

@router.get("")
async def list_resumes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()))
    resumes = result.scalars().all()
    return [{"id": r.id, "filename": r.filename, "created_at": r.created_at.isoformat()} for r in resumes]