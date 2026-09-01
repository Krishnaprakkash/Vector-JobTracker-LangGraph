import asyncio
from redis.asyncio import Redis

from app.config import settings
from app.groq_client import call_groq, MODELS, GroqError

redis = Redis.from_url(settings.redis_url, decode_responses=True)

# (rpm, rpd, tpm, tpd) — tpd=None means no daily token cap
LIMITS = {
    "openai/gpt-oss-20b": (30, 1000, 8000, 200_000),
    "qwen/qwen3.6-27b": (30, 1000, 8000, 200_000),
    "qwen/qwen3.8-27b": (30, 1000, 8000, 200_000),
    "groq/compound-mini": (30, 250, 70_000, None),
    "openai/gpt-oss-120b": (30, 1000, 8000, 200_000),
}

# roles allowed to fall back to gpt-oss-120b on rate-limit
FALLBACK_ELIGIBLE = {"extract", "score", "reason"}


def _keys(model: str):
    return {
        "rpm": f"rl:{model}:rpm",
        "rpd": f"rl:{model}:rpd",
        "tpm": f"rl:{model}:tpm",
        "tpd": f"rl:{model}:tpd",
    }


async def _remaining_ratio(model: str) -> dict[str, float]:
    rpm_cap, rpd_cap, tpm_cap, tpd_cap = LIMITS[model]
    k = _keys(model)
    vals = await redis.mget(k["rpm"], k["rpd"], k["tpm"], k["tpd"])
    rpm_used, rpd_used, tpm_used, tpd_used = (int(v) if v else 0 for v in vals)

    ratios = {
        "rpm": 1 - (rpm_used / rpm_cap),
        "rpd": 1 - (rpd_used / rpd_cap),
        "tpm": 1 - (tpm_used / tpm_cap),
        "tpd": 1.0 if tpd_cap is None else 1 - (tpd_used / tpd_cap),
    }
    return ratios


async def _has_headroom(model: str, est_tokens: int) -> bool:
    rpm_cap, rpd_cap, tpm_cap, tpd_cap = LIMITS[model]
    k = _keys(model)
    vals = await redis.mget(k["rpm"], k["rpd"], k["tpm"], k["tpd"])
    rpm_used, rpd_used, tpm_used, tpd_used = (int(v) if v else 0 for v in vals)

    if rpm_used + 1 > rpm_cap:
        return False
    if rpd_used + 1 > rpd_cap:
        return False
    if tpm_used + est_tokens > tpm_cap:
        return False
    if tpd_cap is not None and tpd_used + est_tokens > tpd_cap:
        return False
    return True


async def _consume(model: str, tokens_used: int):
    k = _keys(model)
    pipe = redis.pipeline()
    pipe.incr(k["rpm"]).expire(k["rpm"], 60)
    pipe.incr(k["rpd"]).expire(k["rpd"], 86400)
    pipe.incrby(k["tpm"], tokens_used).expire(k["tpm"], 60)
    pipe.incrby(k["tpd"], tokens_used).expire(k["tpd"], 86400)
    await pipe.execute()


async def _fallback_ok(fallback_model: str) -> bool:
    ratios = await _remaining_ratio(fallback_model)
    return all(r >= 0.5 for r in ratios.values())


async def route_call(
    role: str, messages: list[dict], est_tokens: int = 500, max_tokens: int = 1024
) -> tuple[str, str]:
    """Returns (content, status). status: 'ok' | 'scoring_failed'."""
    model = MODELS[role]

    if not await _has_headroom(model, est_tokens):
        return await _try_fallback(role, messages, est_tokens, max_tokens, reason="rate_capped")

    try:
        content = await call_groq(role, messages, max_tokens=max_tokens)
        await _consume(model, est_tokens)
        return content, "ok"
    except GroqError:
        return await _try_fallback(role, messages, est_tokens, max_tokens, reason="groq_error")


async def _try_fallback(
    role: str, messages: list[dict], est_tokens: int, max_tokens: int, reason: str
) -> tuple[str, str]:
    if role not in FALLBACK_ELIGIBLE:
        await _schedule_retry(role, messages, est_tokens, max_tokens)
        return "", "scoring_failed"

    fallback_model = MODELS["fallback"]
    if not await _fallback_ok(fallback_model):
        await _schedule_retry(role, messages, est_tokens, max_tokens)
        return "", "scoring_failed"

    try:
        content = await call_groq("fallback", messages, max_tokens=max_tokens)
        await _consume(fallback_model, est_tokens)
        return content, "ok"
    except GroqError:
        await _schedule_retry(role, messages, est_tokens, max_tokens)
        return "", "scoring_failed"


async def _schedule_retry(role: str, messages: list[dict], est_tokens: int, max_tokens: int):
    # Soft retry marker in Redis; actual retry consumer implemented in Phase 4 job queue.
    await redis.setex(f"retry:{role}:{id(messages)}", 30, "pending")