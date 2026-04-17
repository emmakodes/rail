import asyncio
import json
import logging
import time
import tracemalloc
from collections import deque
from functools import partial

import httpx
import psutil
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body, Request
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.orm import Session, selectinload

from app.cache import (
    acquire_todo_list_cache_lock,
    get_todo_list_cache,
    get_todo_list_cache_ttl,
    invalidate_todo_list_cache,
    release_todo_list_cache_lock,
    set_todo_list_cache,
    wait_for_todo_list_cache,
)
from app.config import settings
from app.db import SessionLocal, engine, get_db, initialize_database, pool_snapshot
from app.models import Todo
from app.observability import (
    configure_logging,
    metrics_response,
    monitor_event_loop_lag,
    record_request_metrics,
)
from app.schemas import TodoCreate, TodoCursorPage, TodoRead, TodoWithTagsRead

configure_logging()
app = FastAPI(title=settings.app_name)
logger = logging.getLogger("app.todos")
memory_logger = logging.getLogger("app.memory")
process = psutil.Process()
LEAKY_REQUEST_BODIES: list[dict] = []
BOUNDED_REQUEST_BODIES: deque[dict] = deque(maxlen=200)
MEMORY_BASELINE_SNAPSHOT: tracemalloc.Snapshot | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    initialize_database()
    tracemalloc.start()
    global MEMORY_BASELINE_SNAPSHOT
    MEMORY_BASELINE_SNAPSHOT = tracemalloc.take_snapshot()
    asyncio.create_task(monitor_event_loop_lag())


@app.middleware("http")
async def observability_middleware(request, call_next):
    return await record_request_metrics(request, call_next)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


def _memory_stats() -> dict[str, int | float]:
    rss_bytes = process.memory_info().rss
    return {
        "rss_bytes": rss_bytes,
        "rss_mb": round(rss_bytes / (1024 * 1024), 2),
        "leaky_items": len(LEAKY_REQUEST_BODIES),
        "bounded_items": len(BOUNDED_REQUEST_BODIES),
    }


@app.get("/memory/status")
def memory_status() -> dict[str, int | float]:
    return _memory_stats()


@app.post("/memory/leak")
async def memory_leak(
    request: Request,
    payload: dict = Body(...),
) -> dict[str, int | float | str]:
    LEAKY_REQUEST_BODIES.append(payload)
    stats = _memory_stats()
    request.state.response_bytes = len(json.dumps(stats, default=str).encode("utf-8"))
    memory_logger.warning(
        "memory leak path appended payload",
        extra={
            "event": "memory_leak",
            "extra_fields": stats,
        },
    )
    return {"status": "ok", **stats}


@app.post("/memory/bounded")
async def memory_bounded(
    request: Request,
    payload: dict = Body(...),
) -> dict[str, int | float | str]:
    BOUNDED_REQUEST_BODIES.append(payload)
    stats = _memory_stats()
    request.state.response_bytes = len(json.dumps(stats, default=str).encode("utf-8"))
    memory_logger.info(
        "bounded memory path stored payload",
        extra={
            "event": "memory_bounded",
            "extra_fields": stats,
        },
    )
    return {"status": "ok", **stats}


@app.post("/memory/reset")
def memory_reset() -> dict[str, int | float | str]:
    LEAKY_REQUEST_BODIES.clear()
    BOUNDED_REQUEST_BODIES.clear()
    global MEMORY_BASELINE_SNAPSHOT
    MEMORY_BASELINE_SNAPSHOT = tracemalloc.take_snapshot()
    return {"status": "ok", **_memory_stats()}


@app.get("/memory/diff")
def memory_diff(limit: int = Query(default=5, ge=1, le=20)) -> dict[str, list[dict[str, int | str | float]]]:
    global MEMORY_BASELINE_SNAPSHOT
    current = tracemalloc.take_snapshot()
    baseline = MEMORY_BASELINE_SNAPSHOT or current
    top_stats = current.compare_to(baseline, "lineno")[:limit]
    payload = {
        "top": [
            {
                "location": str(stat.traceback[0]),
                "size_kb": round(stat.size_diff / 1024, 2),
                "count_diff": stat.count_diff,
            }
            for stat in top_stats
        ]
    }
    return payload


@app.get("/cache/todos/status")
def get_todo_cache_status() -> dict[str, int | bool | None]:
    ttl = get_todo_list_cache_ttl()
    return {
        "cache_present": ttl is not None and ttl >= 0,
        "ttl_seconds": ttl,
    }


@app.get("/cache/todos/reset")
def reset_todo_cache() -> dict[str, str]:
    invalidate_todo_list_cache()
    return {"status": "ok"}


@app.get("/loop/fast")
async def loop_fast() -> dict[str, str]:
    await asyncio.sleep(0.01)
    return {"status": "ok"}


@app.get("/loop/blocking")
async def loop_blocking(
    block_seconds: float = Query(default=1.0, ge=0.1, le=10.0),
) -> dict[str, float | str]:
    time.sleep(block_seconds)
    return {"status": "ok", "block_seconds": block_seconds}


@app.get("/loop/blocking-fixed")
async def loop_blocking_fixed(
    block_seconds: float = Query(default=1.0, ge=0.1, le=10.0),
) -> dict[str, float | str]:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, partial(time.sleep, block_seconds))
    return {"status": "ok", "block_seconds": block_seconds}


@app.get("/pool/status")
def get_pool_status() -> dict[str, str | int | float]:
    return pool_snapshot()


@app.get("/pool/pg-stat-activity")
def get_pg_stat_activity(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, str | int | None]]]:
    db.info["query_count"] = db.info.get("query_count", 0) + 1
    request.state.db_query_count = db.info["query_count"]
    rows = db.execute(
        text(
            """
            SELECT
              state,
              wait_event_type,
              COUNT(*)::int AS connection_count
            FROM pg_stat_activity
            WHERE datname = current_database()
            GROUP BY state, wait_event_type
            ORDER BY connection_count DESC, state NULLS LAST
            """
        )
    ).mappings().all()
    payload = {"connections": [dict(row) for row in rows]}
    request.state.response_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    return payload


@app.get("/pool/exhaust")
def exhaust_pool(
    request: Request,
    hold_seconds: int = Query(default=5, ge=1, le=30),
    db: Session = Depends(get_db),
) -> dict[str, str | int | float]:
    db.info["query_count"] = db.info.get("query_count", 0) + 1
    request.state.db_query_count = db.info["query_count"]
    started_at = time.perf_counter()
    try:
        # Force checkout, then keep the connection occupied with a DB-side sleep.
        db.execute(text("SELECT pg_sleep(:hold_seconds)"), {"hold_seconds": hold_seconds})
    except SATimeoutError as exc:
        logger.warning(
            "pool checkout timed out",
            extra={
                "event": "pool_exhaustion",
                "extra_fields": {
                    "hold_seconds": hold_seconds,
                    **pool_snapshot(),
                },
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot acquire connection from pool",
        ) from exc

    elapsed = round(time.perf_counter() - started_at, 2)
    payload = {
        "status": "ok",
        "hold_seconds": hold_seconds,
        "elapsed_seconds": elapsed,
        **pool_snapshot(),
    }
    request.state.response_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    logger.info(
        "pool drill completed",
        extra={
            "event": "pool_exhaustion",
            "extra_fields": payload,
        },
    )
    return payload


@app.get("/pool/exhaust-fixed")
def exhaust_pool_fixed(
    request: Request,
    wait_seconds: int = Query(default=5, ge=1, le=30),
) -> dict[str, str | int | float]:
    started_at = time.perf_counter()

    # Simulate slow non-DB work first. No DB session is opened yet.
    time.sleep(wait_seconds)

    db = SessionLocal()
    db.info["query_count"] = 0
    try:
        db.info["query_count"] += 1
        request.state.db_query_count = db.info["query_count"]
        db.execute(text("SELECT 1"))
    except SATimeoutError as exc:
        logger.warning(
            "pool checkout timed out on fixed path",
            extra={
                "event": "pool_exhaustion_fixed",
                "extra_fields": {
                    "wait_seconds": wait_seconds,
                    **pool_snapshot(),
                },
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot acquire connection from pool",
        ) from exc
    finally:
        db.close()

    elapsed = round(time.perf_counter() - started_at, 2)
    payload = {
        "status": "ok",
        "wait_seconds": wait_seconds,
        "elapsed_seconds": elapsed,
        **pool_snapshot(),
    }
    request.state.response_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    logger.info(
        "pool drill fixed path completed",
        extra={
            "event": "pool_exhaustion_fixed",
            "extra_fields": payload,
        },
    )
    return payload


@app.get("/todos", response_model=list[TodoRead] | list[TodoWithTagsRead])
async def list_todos(
    request: Request,
    search: str | None = Query(default=None, min_length=1, max_length=120),
    search_mode: str = Query(default="all", pattern="^(all|contains|exact)$"),
    include_tags: bool = Query(default=False),
    tag_load_strategy: str = Query(default="n_plus_one", pattern="^(n_plus_one|selectin)$"),
    cache_strategy: str = Query(default="plain", pattern="^(plain|jitter|lock)$"),
    disable_pagination: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=5000),
    db: Session = Depends(get_db),
) -> list[Todo] | list[dict]:
    def count_query() -> None:
        db.info["query_count"] = db.info.get("query_count", 0) + 1
        request.state.db_query_count = db.info["query_count"]

    use_cache = (
        search is None
        and search_mode == "all"
        and offset == 0
        and limit == 50
        and not include_tags
        and not disable_pagination
    )
    request.state.cache_status = "bypass"
    cached_todos = get_todo_list_cache() if use_cache else None
    if cached_todos is not None:
        request.state.cache_status = "hit"
        logger.info(
            "todos served from cache",
            extra={
                "event": "list_todos",
                "extra_fields": {
                    "todo_count": len(cached_todos),
                    "cache_status": "hit",
                    "cache_strategy": cache_strategy,
                    "search_mode": search_mode,
                    "search": search,
                    "include_tags": include_tags,
                    "tag_load_strategy": tag_load_strategy,
                    "disable_pagination": disable_pagination,
                    "limit": limit,
                    "offset": offset,
                    "delay_seconds": settings.todo_read_delay_seconds,
                },
            },
        )
        return cached_todos

    async def rebuild_todos_payload() -> tuple[list[Todo] | list[dict], list[Todo]]:
        if settings.todo_cache_rebuild_delay_seconds > 0:
            await asyncio.sleep(settings.todo_cache_rebuild_delay_seconds)

        query = db.query(Todo).order_by(Todo.id.desc())
        if search is not None:
            if search_mode == "contains":
                query = query.filter(Todo.title.ilike(f"%{search}%"))
            elif search_mode == "exact":
                query = query.filter(Todo.title == search)

        if include_tags and tag_load_strategy == "selectin":
            query = query.options(selectinload(Todo.tags))

        count_query()
        if disable_pagination:
            todos = query.all()
        else:
            todos = query.offset(offset).limit(limit).all()

        if include_tags:
            if tag_load_strategy == "n_plus_one":
                payload = []
                for todo in todos:
                    count_query()
                    payload.append(
                        {
                            "id": todo.id,
                            "title": todo.title,
                            "created_at": todo.created_at,
                            "tags": [{"id": tag.id, "label": tag.label} for tag in todo.tags],
                        }
                    )
            else:
                count_query()
                payload = [
                    {
                        "id": todo.id,
                        "title": todo.title,
                        "created_at": todo.created_at,
                        "tags": [{"id": tag.id, "label": tag.label} for tag in todo.tags],
                    }
                    for todo in todos
                ]
        else:
            payload = jsonable_encoder(todos)
        return payload, todos

    if settings.todo_upstream_url:
        try:
            async with httpx.AsyncClient() as client:
                upstream_response = await asyncio.wait_for(
                    client.get(settings.todo_upstream_url),
                    timeout=settings.todo_upstream_timeout_seconds,
                )
            upstream_response.raise_for_status()
        except (TimeoutError, httpx.HTTPError):
            logger.warning(
                "todo upstream timed out or failed",
                extra={
                    "event": "todo_upstream_timeout",
                    "extra_fields": {
                        "upstream_url": settings.todo_upstream_url,
                        "timeout_seconds": settings.todo_upstream_timeout_seconds,
                    },
                },
            )

    if settings.todo_read_delay_seconds > 0:
        logger.warning(
            "todo latency injection active",
            extra={
                "event": "latency_injection",
                "extra_fields": {
                    "path": "/todos",
                    "delay_seconds": settings.todo_read_delay_seconds,
                },
            },
        )
        time.sleep(settings.todo_read_delay_seconds)

    if use_cache and cache_strategy == "lock":
        lock_token = acquire_todo_list_cache_lock()
        if lock_token is not None:
            request.state.cache_status = "lock_rebuild"
            try:
                payload, todos = await rebuild_todos_payload()
                set_todo_list_cache(payload, use_jitter=True)
            finally:
                release_todo_list_cache_lock(lock_token)
        else:
            request.state.cache_status = "lock_wait"
            waited_payload = wait_for_todo_list_cache()
            if waited_payload is not None:
                logger.info(
                    "todos served after cache wait",
                    extra={
                        "event": "list_todos",
                        "extra_fields": {
                            "todo_count": len(waited_payload),
                            "cache_status": "lock_wait_hit",
                            "cache_strategy": cache_strategy,
                            "search_mode": search_mode,
                            "search": search,
                            "include_tags": include_tags,
                            "tag_load_strategy": tag_load_strategy,
                            "disable_pagination": disable_pagination,
                            "limit": limit,
                            "offset": offset,
                            "delay_seconds": settings.todo_read_delay_seconds,
                        },
                    },
                )
                request.state.cache_status = "lock_wait_hit"
                return waited_payload
            request.state.cache_status = "lock_wait_fallback"
            payload, todos = await rebuild_todos_payload()
            set_todo_list_cache(payload, use_jitter=True)
    else:
        request.state.cache_status = "miss" if use_cache else "bypass"
        payload, todos = await rebuild_todos_payload()
        if use_cache:
            set_todo_list_cache(payload, use_jitter=(cache_strategy == "jitter"))

    request.state.response_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    logger.info(
        "todos listed",
        extra={
            "event": "list_todos",
            "extra_fields": {
                "todo_count": len(todos),
                "cache_status": request.state.cache_status,
                "cache_strategy": cache_strategy,
                "search_mode": search_mode,
                "search": search,
                "include_tags": include_tags,
                "tag_load_strategy": tag_load_strategy,
                "disable_pagination": disable_pagination,
                "limit": limit,
                "offset": offset,
                "delay_seconds": settings.todo_read_delay_seconds,
                "response_bytes": request.state.response_bytes,
            },
        },
    )
    return payload


@app.get("/todos/cursor", response_model=TodoCursorPage)
def list_todos_cursor(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> dict:
    db.info["query_count"] = db.info.get("query_count", 0) + 1
    request.state.db_query_count = db.info["query_count"]

    query = db.query(Todo).order_by(Todo.id.desc())
    if cursor is not None:
        query = query.filter(Todo.id < cursor)

    todos = query.limit(limit + 1).all()
    has_more = len(todos) > limit
    visible = todos[:limit]
    next_cursor = visible[-1].id if has_more and visible else None

    payload = {
        "items": jsonable_encoder(visible),
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
    request.state.response_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    logger.info(
        "todos cursor listed",
        extra={
            "event": "list_todos_cursor",
            "extra_fields": {
                "todo_count": len(visible),
                "limit": limit,
                "cursor": cursor,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "response_bytes": request.state.response_bytes,
            },
        },
    )
    return payload


@app.get("/todos/explain", include_in_schema=False)
def explain_todos_query(
    request: Request,
    search: str = Query(..., min_length=1, max_length=120),
    search_mode: str = Query(default="contains", pattern="^(contains|exact)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=5000),
    db: Session = Depends(get_db),
) -> dict[str, list[str]]:
    db.info["query_count"] = db.info.get("query_count", 0) + 1
    request.state.db_query_count = db.info["query_count"]
    if search_mode == "contains":
        statement = text(
            """
            EXPLAIN ANALYZE
            SELECT id, title, created_at
            FROM todos
            WHERE title ILIKE :pattern
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
            """
        )
        params = {"pattern": f"%{search}%", "limit": limit, "offset": offset}
    else:
        statement = text(
            """
            EXPLAIN ANALYZE
            SELECT id, title, created_at
            FROM todos
            WHERE title = :title
            ORDER BY id DESC
            LIMIT :limit OFFSET :offset
            """
        )
        params = {"title": search, "limit": limit, "offset": offset}

    rows = db.execute(statement, params).all()
    plan = [row[0] for row in rows]
    logger.info(
        "todos explain analyzed",
        extra={
            "event": "explain_todos",
            "extra_fields": {
                "search_mode": search_mode,
                "search": search,
                "limit": limit,
                "offset": offset,
            },
        },
    )
    return {"plan": plan}


@app.post("/todos", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate, db: Session = Depends(get_db)) -> Todo:
    db.info["query_count"] = db.info.get("query_count", 0) + 1
    todo = Todo(title=payload.title.strip())
    db.add(todo)
    db.commit()
    db.refresh(todo)
    invalidate_todo_list_cache()
    logger.info(
        "todo created",
        extra={
            "event": "create_todo",
            "extra_fields": {
                "todo_id": todo.id,
                "title_length": len(todo.title),
            },
        },
    )
    return todo
