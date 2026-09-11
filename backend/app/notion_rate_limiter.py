import asyncio
import time

import redis.asyncio as aioredis

from .config import settings

MIN_INTERVAL_SECONDS = 1.0 / 3
THROTTLE_KEY_TTL = 60

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def throttle_notion(workspace_id: str) -> None:
    """Blocks until at least MIN_INTERVAL_SECONDS have passed since this user's
    (workspace's) last Notion API call. Calls within a single background task are
    sequential, so this simple last-call-timestamp approach is sufficient — no need
    for a full token bucket."""
    r = _get_redis()
    key = f"notion_throttle:{workspace_id}"

    last_str = await r.get(key)
    now = time.time()
    if last_str:
        elapsed = now - float(last_str)
        if elapsed < MIN_INTERVAL_SECONDS:
            await asyncio.sleep(MIN_INTERVAL_SECONDS - elapsed)

    await r.set(key, str(time.time()), ex=THROTTLE_KEY_TTL)