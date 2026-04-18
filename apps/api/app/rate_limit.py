from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import Request
from redis.exceptions import RedisError

from app.cache import redis_client
from app.config import settings

logger = logging.getLogger("app.rate_limit")


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    current: int
    key: str


def client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def check_todo_create_rate_limit(request: Request) -> RateLimitResult | None:
    limit = settings.todo_create_rate_limit_per_minute
    if limit <= 0 or redis_client is None:
        return None

    client_ip = client_ip_from_request(request)
    window_seconds = 60
    now = int(time.time())
    window_start = now - (now % window_seconds)
    reset_seconds = window_seconds - (now - window_start)
    key = f"ratelimit:todos:create:{client_ip}:{window_start}"

    try:
        current = int(redis_client.incr(key))
        if current == 1:
            redis_client.expire(key, window_seconds)
    except RedisError:
        logger.warning(
            "rate limit check failed",
            extra={
                "event": "rate_limit_failed_open",
                "extra_fields": {
                    "client_ip": client_ip,
                    "limit": limit,
                },
            },
        )
        return None

    remaining = max(limit - current, 0)
    return RateLimitResult(
        allowed=current <= limit,
        limit=limit,
        remaining=remaining,
        reset_seconds=reset_seconds,
        current=current,
        key=key,
    )
