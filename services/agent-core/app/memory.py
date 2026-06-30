"""Conversation memory backed by Redis (a sliding window per conversation).

Stateless agent pods + shared Redis means any replica can serve any turn — the
memory module is what makes the service horizontally scalable.
"""

from __future__ import annotations

import json

import redis.asyncio as redis

from agent_common.schemas import ChatMessage
from app.settings import settings

_redis = redis.from_url(settings.redis_url, decode_responses=True)
_TTL_SECONDS = 60 * 60 * 24  # 1 day


def _key(conversation_id: str) -> str:
    return f"conv:{conversation_id}"


async def load_history(conversation_id: str) -> list[ChatMessage]:
    raw = await _redis.lrange(_key(conversation_id), -settings.memory_window, -1)
    return [ChatMessage.model_validate(json.loads(r)) for r in raw]


async def append(conversation_id: str, message: ChatMessage) -> None:
    key = _key(conversation_id)
    await _redis.rpush(key, json.dumps(message.model_dump(mode="json")))
    await _redis.ltrim(key, -settings.memory_window * 2, -1)
    await _redis.expire(key, _TTL_SECONDS)
