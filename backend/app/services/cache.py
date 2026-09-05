"""Redis cache helpers: JSON get/set with TTL (PROJECT_PLAN.md §4)."""

import json
from typing import Any

from redis.asyncio import Redis


async def cache_get_json(redis: Redis, key: str) -> Any | None:
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set_json(redis: Redis, key: str, value: Any, ttl_seconds: int) -> None:
    await redis.set(key, json.dumps(value), ex=ttl_seconds)
