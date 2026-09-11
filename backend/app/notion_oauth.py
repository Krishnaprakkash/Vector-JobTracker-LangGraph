import secrets
from urllib.parse import urlencode

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from .config import settings
from .db import get_db
from .auth import create_session, set_session_cookie
from .models import User
from .notion_setup import run_notion_setup

router = APIRouter(prefix="/api/notion", tags=["notion"])

NOTION_AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
NOTION_TOKEN_URL = "https://api.notion.com/v1/oauth/token"

STATE_TTL_SECONDS = 600

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


@router.get("/authorize")
async def notion_authorize():
    state = secrets.token_urlsafe(24)
    r = _get_redis()
    await r.set(f"notion_oauth_state:{state}", "1", ex=STATE_TTL_SECONDS)

    params = {
        "client_id": settings.notion_client_id,
        "redirect_uri": settings.notion_redirect_uri,
        "response_type": "code",
        "owner": "user",
        "state": state,
    }
    return RedirectResponse(f"{NOTION_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
async def notion_callback(
    code: str,
    state: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    r = _get_redis()
    if not await r.get(f"notion_oauth_state:{state}"):
        raise HTTPException(400, "Invalid or expired state")
    await r.delete(f"notion_oauth_state:{state}")

    auth = (settings.notion_client_id, settings.notion_client_secret)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            NOTION_TOKEN_URL,
            auth=auth,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.notion_redirect_uri,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(400, f"Notion token exchange failed: {resp.text}")

    data = resp.json()
    workspace_id = data["workspace_id"]
    access_token = data["access_token"]
    bot_id = data.get("bot_id")
    email = (data.get("owner", {}).get("user", {}).get("person", {}) or {}).get("email")

    result = await db.execute(select(User).where(User.notion_workspace_id == workspace_id))
    user = result.scalar_one_or_none()

    if user:
        user.notion_access_token = access_token
        user.notion_bot_id = bot_id
        if email:
            user.email = email
    else:
        user = User(
            notion_workspace_id=workspace_id,
            notion_access_token=access_token,
            notion_bot_id=bot_id,
            email=email,
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    session_token = await create_session(user.id)
    set_session_cookie(response, session_token)

    setup_result = await run_notion_setup(user, db)

    return {"status": "connected", "user_id": user.id, "setup": setup_result}