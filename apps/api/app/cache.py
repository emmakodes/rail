from __future__ import annotations

import json
import logging

from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("app.cache")
TODO_LIST_CACHE_KEY = "todos:list"

redis_client = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None


def get_todo_list_cache() -> list[dict] | None:
    if redis_client is None:
        return None

    try:
        raw = redis_client.get(TODO_LIST_CACHE_KEY)
        if raw is None:
            return None
        return json.loads(raw)
    except RedisError:
        logger.warning(
            "todo cache read failed",
            extra={
                "event": "todo_cache_read_failed",
                "extra_fields": {
                    "cache_key": TODO_LIST_CACHE_KEY,
                },
            },
        )
        return None


def set_todo_list_cache(payload: list[dict]) -> None:
    if redis_client is None:
        return

    try:
        redis_client.setex(
            TODO_LIST_CACHE_KEY,
            settings.todo_cache_ttl_seconds,
            json.dumps(payload),
        )
    except RedisError:
        logger.warning(
            "todo cache write failed",
            extra={
                "event": "todo_cache_write_failed",
                "extra_fields": {
                    "cache_key": TODO_LIST_CACHE_KEY,
                    "ttl_seconds": settings.todo_cache_ttl_seconds,
                },
            },
        )


def invalidate_todo_list_cache() -> None:
    if redis_client is None:
        return

    try:
        redis_client.delete(TODO_LIST_CACHE_KEY)
    except RedisError:
        logger.warning(
            "todo cache invalidation failed",
            extra={
                "event": "todo_cache_invalidation_failed",
                "extra_fields": {
                    "cache_key": TODO_LIST_CACHE_KEY,
                },
            },
        )
