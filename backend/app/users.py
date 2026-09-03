import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import User

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/me")
async def get_me(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return {"id": user.id, "email": user.email, "last_search_query": user.last_search_query}


@router.patch("/me")
async def update_me(user_id: uuid.UUID, last_search_query: str, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if last_search_query.strip():  # only update if non-empty, per spec
        user.last_search_query = last_search_query.strip()
        await db.commit()
    return {"last_search_query": user.last_search_query}