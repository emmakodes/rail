from __future__ import annotations

import json
import logging
import random
import time
import uuid

from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger("app.cache")
TODO_LIST_CACHE_KEY = "todos:list"
TODO_LIST_CACHE_LOCK_KEY = f"{TODO_LIST_CACHE_KEY}:lock"
STARTUP_TODO_WARM_LOCK_KEY = "startup:todos:warm:lock"
STARTUP_TODO_WARM_DONE_KEY = "startup:todos:warm:done"

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


def _cache_ttl(use_jitter: bool) -> int:
    ttl = settings.todo_cache_ttl_seconds
    if use_jitter and settings.todo_cache_ttl_jitter_seconds > 0:
        ttl += random.randint(0, settings.todo_cache_ttl_jitter_seconds)
    return ttl


def set_todo_list_cache(payload: list[dict], *, use_jitter: bool = False) -> None:
    if redis_client is None:
        return

    try:
        ttl = _cache_ttl(use_jitter)
        redis_client.setex(
            TODO_LIST_CACHE_KEY,
            ttl,
            json.dumps(payload, default=str),
        )
    except RedisError:
        logger.warning(
            "todo cache write failed",
            extra={
                "event": "todo_cache_write_failed",
                "extra_fields": {
                    "cache_key": TODO_LIST_CACHE_KEY,
                    "ttl_seconds": _cache_ttl(use_jitter),
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


def get_todo_list_cache_ttl() -> int | None:
    if redis_client is None:
        return None

    try:
        return int(redis_client.ttl(TODO_LIST_CACHE_KEY))
    except RedisError:
        return None


def acquire_todo_list_cache_lock() -> str | None:
    if redis_client is None:
        return None

    token = str(uuid.uuid4())
    try:
        acquired = redis_client.set(
            TODO_LIST_CACHE_LOCK_KEY,
            token,
            nx=True,
            ex=max(1, int(settings.todo_cache_lock_timeout_seconds)),
        )
        return token if acquired else None
    except RedisError:
        return None


def release_todo_list_cache_lock(token: str) -> None:
    if redis_client is None:
        return

    try:
        current = redis_client.get(TODO_LIST_CACHE_LOCK_KEY)
        if current == token:
            redis_client.delete(TODO_LIST_CACHE_LOCK_KEY)
    except RedisError:
        logger.warning(
            "todo cache lock release failed",
            extra={
                "event": "todo_cache_lock_release_failed",
                "extra_fields": {
                    "cache_key": TODO_LIST_CACHE_KEY,
                },
            },
        )


def wait_for_todo_list_cache() -> list[dict] | None:
    if redis_client is None:
        return None

    deadline = time.perf_counter() + settings.todo_cache_lock_wait_timeout_seconds
    while time.perf_counter() < deadline:
        cached = get_todo_list_cache()
        if cached is not None:
            return cached
        time.sleep(settings.todo_cache_lock_poll_seconds)
    return None


def acquire_startup_todo_warm_lock() -> str | None:
    if redis_client is None:
        return None

    token = str(uuid.uuid4())
    try:
        acquired = redis_client.set(
            STARTUP_TODO_WARM_LOCK_KEY,
            token,
            nx=True,
            ex=max(1, int(settings.startup_warm_lock_timeout_seconds)),
        )
        return token if acquired else None
    except RedisError:
        return None


def release_startup_todo_warm_lock(token: str) -> None:
    if redis_client is None:
        return

    try:
        current = redis_client.get(STARTUP_TODO_WARM_LOCK_KEY)
        if current == token:
            redis_client.delete(STARTUP_TODO_WARM_LOCK_KEY)
    except RedisError:
        logger.warning(
            "startup warm lock release failed",
            extra={
                "event": "startup_warm_lock_release_failed",
                "extra_fields": {
                    "cache_key": STARTUP_TODO_WARM_LOCK_KEY,
                },
            },
        )


def mark_startup_todo_warm_done(payload: dict[str, str | int | float]) -> None:
    if redis_client is None:
        return

    try:
        redis_client.setex(
            STARTUP_TODO_WARM_DONE_KEY,
            max(60, int(settings.todo_cache_ttl_seconds)),
            json.dumps(payload),
        )
    except RedisError:
        logger.warning(
            "startup warm done marker write failed",
            extra={
                "event": "startup_warm_done_write_failed",
                "extra_fields": {
                    "cache_key": STARTUP_TODO_WARM_DONE_KEY,
                },
            },
        )


def get_startup_todo_warm_done() -> dict | None:
    if redis_client is None:
        return None

    try:
        raw = redis_client.get(STARTUP_TODO_WARM_DONE_KEY)
        if raw is None:
            return None
        return json.loads(raw)
    except RedisError:
        return None


def clear_startup_todo_warm_state() -> None:
    if redis_client is None:
        return

    try:
        redis_client.delete(STARTUP_TODO_WARM_LOCK_KEY, STARTUP_TODO_WARM_DONE_KEY)
    except RedisError:
        logger.warning(
            "startup warm state clear failed",
            extra={
                "event": "startup_warm_state_clear_failed",
                "extra_fields": {
                    "cache_key": STARTUP_TODO_WARM_DONE_KEY,
                },
            },
        )
