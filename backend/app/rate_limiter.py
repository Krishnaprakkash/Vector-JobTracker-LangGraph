import time
from redis.asyncio import Redis

from app.config import settings
from app.groq_client import call_groq, MODELS, GroqError

redis = Redis.from_url(settings.redis_url, decode_responses=True)

LIMITS = {
    "openai/gpt-oss-20b": (30, 1000, 8000, 200_000),
    "qwen/qwen3.6-27b": (30, 1000, 8000, 200_000),
    "qwen/qwen3.8-27b": (30, 1000, 8000, 200_000),
    "groq/compound-mini": (30, 250, 70_000, None),
    "groq/compound": (30, 250, 70_000, None),
    "openai/gpt-oss-120b": (30, 1000, 8000, 200_000),
}


def _keys(model: str):
    return {
        "rpm": f"rl:{model}:rpm",
        "rpd": f"rl:{model}:rpd",
        "tpm": f"rl:{model}:tpm",
        "tpd": f"rl:{model}:tpd",
    }


async def _headroom_check(model: str, est_tokens: int) -> tuple[bool, str | None]:
    """Returns (has_headroom, blocking_dimension). blocking_dimension in {'rpm','rpd','tpm','tpd'} or None."""
    rpm_cap, rpd_cap, tpm_cap, tpd_cap = LIMITS[model]
    k = _keys(model)
    vals = await redis.mget(k["rpm"], k["rpd"], k["tpm"], k["tpd"])
    rpm_used, rpd_used, tpm_used, tpd_used = (int(v) if v else 0 for v in vals)

    if rpm_used + 1 > rpm_cap:
        return False, "rpm"
    if rpd_used + 1 > rpd_cap:
        return False, "rpd"
    if tpm_used + est_tokens > tpm_cap:
        return False, "tpm"
    if tpd_cap is not None and tpd_used + est_tokens > tpd_cap:
        return False, "tpd"
    return True, None


async def _reset_time(model: str, dimension: str) -> int:
    """Returns unix timestamp when the blocking dimension's Redis key expires (i.e. resets)."""
    key = _keys(model)[dimension]
    ttl = await redis.ttl(key)
    if ttl is None or ttl < 0:
        return int(time.time())  # key has no TTL / doesn't exist — treat as available now
    return int(time.time()) + ttl


async def _consume(model: str, tokens_used: int):
    k = _keys(model)
    pipe = redis.pipeline()
    pipe.incr(k["rpm"]).expire(k["rpm"], 60)
    pipe.incr(k["rpd"]).expire(k["rpd"], 86400)
    pipe.incrby(k["tpm"], tokens_used).expire(k["tpm"], 60)
    pipe.incrby(k["tpd"], tokens_used).expire(k["tpd"], 86400)
    await pipe.execute()


async def route_call(
    role: str, messages: list[dict], est_tokens: int = 500, max_tokens: int = 1024
) -> dict:
    """Returns {"status": "ok", "content": str} or
              {"status": "quota_exceeded", "reset_at": int (unix ts)}"""
    model = MODELS[role]

    has_headroom, blocking_dim = await _headroom_check(model, est_tokens)
    if not has_headroom:
        reset_at = await _reset_time(model, blocking_dim)
        return {"status": "quota_exceeded", "reset_at": reset_at}

    try:
        content = await call_groq(role, messages, max_tokens=max_tokens)
        await _consume(model, est_tokens)
        return {"status": "ok", "content": content}
    except GroqError:
        reset_at = int(time.time()) + 30  # generic short backoff on transient Groq error
        return {"status": "quota_exceeded", "reset_at": reset_at}