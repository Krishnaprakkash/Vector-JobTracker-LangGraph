import json
import re
import redis.asyncio as redis

from .config import settings

TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def build_cache_key(title: str, location: str, seniority: str) -> str:
    return f"comp:{_normalize(title)}:{_normalize(location)}:{_normalize(seniority)}"


async def get_cached_comp(title: str, location: str, seniority: str) -> dict | None:
    key = build_cache_key(title, location, seniority)
    r = _get_redis()
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def set_cached_comp(title: str, location: str, seniority: str, comp: dict) -> None:
    key = build_cache_key(title, location, seniority)
    r = _get_redis()
    await r.set(key, json.dumps(comp), ex=TTL_SECONDS)