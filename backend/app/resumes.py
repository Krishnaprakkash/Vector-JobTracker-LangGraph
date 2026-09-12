import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .auth import get_current_user
from .models import Resume, User

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

RESUME_DIR = os.path.join(settings.STORAGE_DIR, "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)


def _resume_path(resume_id: uuid.UUID) -> str:
    return os.path.join(RESUME_DIR, f"{resume_id}.pdf")


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
    return [{"id": r.id, "job_id": r.job_id, "filename": r.filename, "created_at": r.created_at.isoformat()} for r in resumes]