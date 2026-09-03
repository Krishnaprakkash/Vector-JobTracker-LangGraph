import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import CoverLetter
from .cover_letter import generate_cover_letter

router = APIRouter(prefix="/api/cover-letters", tags=["cover-letters"])


@router.post("")
async def create_cover_letter(job_id: uuid.UUID, resume_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    letter = await generate_cover_letter(db, job_id, resume_id)
    if not letter:
        raise HTTPException(400, "Could not generate cover letter — check job/resume exist")
    return {
        "id": letter.id,
        "content": letter.content,
        "iteration_count": letter.iteration_count,
        "needs_manual_edit": letter.needs_manual_edit,
    }


@router.get("/{letter_id}/file")
async def get_cover_letter_pdf(letter_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    letter = await db.get(CoverLetter, letter_id)
    if not letter or not letter.pdf_path:
        raise HTTPException(404, "Cover letter not found")
    return FileResponse(letter.pdf_path, media_type="application/pdf", filename=f"cover_letter_{letter_id}.pdf")