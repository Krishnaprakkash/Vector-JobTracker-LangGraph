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
    return {"id": user.id, "email": user.email, "last_search_query": user.last_search_query, "home_location": user.home_location}


@router.patch("/me")
async def update_me(
    user_id: uuid.UUID,
    last_search_query: str | None = None,
    home_location: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if last_search_query and last_search_query.strip():
        user.last_search_query = last_search_query.strip()
    if home_location is not None:  # allow explicit clearing with empty string
        user.home_location = home_location.strip() or None
    await db.commit()
    return {"last_search_query": user.last_search_query, "home_location": user.home_location}