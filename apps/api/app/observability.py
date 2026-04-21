from __future__ import annotations

import json
import logging
import sys
import time
import uuid
import asyncio
from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


http_requests_total = Counter(
    "todo_http_requests_total",
    "Total HTTP requests handled by the API.",
    ("method", "path", "status_code"),
)
http_request_duration_seconds = Histogram(
    "todo_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
event_loop_lag_seconds = Histogram(
    "todo_event_loop_lag_seconds",
    "Observed event loop lag in seconds.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def monitor_event_loop_lag(
    *,
    interval_seconds: float = 0.1,
    warning_threshold_ms: float = 250,
) -> None:
    logger = logging.getLogger("app.event_loop")
    while True:
        started_at = time.perf_counter()
        await asyncio.sleep(interval_seconds)
        elapsed = time.perf_counter() - started_at
        lag = max(elapsed - interval_seconds, 0)
        event_loop_lag_seconds.observe(lag)
        lag_ms = round(lag * 1000, 2)
        if lag_ms >= warning_threshold_ms:
            logger.warning(
                "event loop lag detected",
                extra={
                    "event": "event_loop_lag",
                    "extra_fields": {
                        "lag_ms": lag_ms,
                        "interval_ms": round(interval_seconds * 1000, 2),
                    },
                },
            )


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


async def record_request_metrics(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request_id_context.set(request_id)
    request.state.db_query_count = 0
    request.state.response_bytes = 0
    request.state.cache_status = "-"
    request.state.rate_limit_limit = None
    request.state.rate_limit_remaining = None
    request.state.rate_limit_reset = None
    request.state.retry_attempts = None
    request.state.circuit_state = None
    started_at = time.perf_counter()
    logger = logging.getLogger("app.request")
    method = request.method

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        elapsed = time.perf_counter() - started_at
        path = _route_template(request)
        http_request_duration_seconds.labels(method=method, path=path).observe(elapsed)
        http_requests_total.labels(method=method, path=path, status_code="500").inc()
        logger.exception(
            "request failed",
            extra={
                "event": "http_request",
                "extra_fields": {
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            },
        )
        raise

    path = _route_template(request)
    elapsed = time.perf_counter() - started_at
    http_request_duration_seconds.labels(method=method, path=path).observe(elapsed)
    http_requests_total.labels(method=method, path=path, status_code=str(status_code)).inc()
    response.headers["x-request-id"] = request_id
    response.headers["x-db-queries"] = str(getattr(request.state, "db_query_count", 0))
    response.headers["x-response-bytes"] = str(getattr(request.state, "response_bytes", 0))
    response.headers["x-cache-status"] = str(getattr(request.state, "cache_status", "-"))
    if getattr(request.state, "rate_limit_limit", None) is not None:
        response.headers["x-rate-limit-limit"] = str(request.state.rate_limit_limit)
        response.headers["x-rate-limit-remaining"] = str(request.state.rate_limit_remaining)
        response.headers["x-rate-limit-reset"] = str(request.state.rate_limit_reset)
    if getattr(request.state, "retry_attempts", None) is not None:
        response.headers["x-retry-attempts"] = str(request.state.retry_attempts)
    if getattr(request.state, "circuit_state", None) is not None:
        response.headers["x-circuit-state"] = str(request.state.circuit_state)

    logger.info(
        "request completed",
        extra={
            "event": "http_request",
            "extra_fields": {
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(elapsed * 1000, 2),
                "db_queries": getattr(request.state, "db_query_count", 0),
                "response_bytes": getattr(request.state, "response_bytes", 0),
                "cache_status": getattr(request.state, "cache_status", "-"),
                "rate_limit_remaining": getattr(request.state, "rate_limit_remaining", None),
                "retry_attempts": getattr(request.state, "retry_attempts", None),
                "circuit_state": getattr(request.state, "circuit_state", None),
                "client_ip": request.client.host if request.client else None,
            },
        },
    )
    return response
