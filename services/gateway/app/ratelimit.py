"""Redis-backed fixed-window rate limiter (per user).

A shared Redis counter means the limit holds across all gateway replicas — a
single user can't bypass it by hitting a different pod.
"""

from __future__ import annotations

import redis.asyncio as redis

from agent_common.errors import RateLimitError
from app.settings import settings

_redis = redis.from_url(settings.redis_url, decode_responses=True)


async def enforce(identity: str) -> None:
    key = f"rl:{identity}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, settings.rate_limit_window_s)
    if count > settings.rate_limit_requests:
        ttl = await _redis.ttl(key)
        raise RateLimitError(
            "请求过于频繁，请稍后再试",
            detail={"retry_after_s": ttl, "limit": settings.rate_limit_requests},
        )
