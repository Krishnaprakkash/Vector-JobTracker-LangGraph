import secrets
import uuid

import redis.asyncio as aioredis
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_db
from .models import User

SESSION_TTL_SECONDS = 30 * 24 * 3600
COOKIE_NAME = "vector_session"

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def create_session(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    r = _get_redis()
    await r.set(f"session:{token}", str(user_id), ex=SESSION_TTL_SECONDS)
    return token


async def destroy_session(token: str) -> None:
    r = _get_redis()
    await r.delete(f"session:{token}")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


async def get_current_user(
    vector_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if settings.dev_mode and not vector_session:
        user = await db.get(User, settings.dev_user_id)
        if not user:
            raise HTTPException(500, "Dev user not seeded")
        return user

    if not vector_session:
        raise HTTPException(401, "Not authenticated")

    r = _get_redis()
    user_id_str = await r.get(f"session:{vector_session}")
    if not user_id_str:
        raise HTTPException(401, "Session expired or invalid")

    user = await db.get(User, uuid.UUID(user_id_str))
    if not user:
        raise HTTPException(401, "User not found")
    return user