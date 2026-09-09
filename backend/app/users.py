from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .auth import get_current_user
from .models import User

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "last_search_query": user.last_search_query,
        "home_location": user.home_location,
        "experience_level": user.experience_level,
    }


@router.patch("/me")
async def update_me(
    last_search_query: str | None = None,
    home_location: str | None = None,
    experience_level: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if last_search_query and last_search_query.strip():
        user.last_search_query = last_search_query.strip()
    if home_location is not None:
        user.home_location = home_location.strip() or None
    if experience_level is not None:
        user.experience_level = experience_level.strip() or None
    await db.commit()
    return {
        "last_search_query": user.last_search_query,
        "home_location": user.home_location,
        "experience_level": user.experience_level,
    }