import logging
import time
import asyncio
import json

import httpx
from fastapi import Depends, FastAPI, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from app.cache import get_todo_list_cache, invalidate_todo_list_cache, set_todo_list_cache
from app.config import settings
from app.db import get_db, initialize_database
from app.models import Todo
from app.observability import configure_logging, metrics_response, record_request_metrics
from app.schemas import TodoCreate, TodoCursorPage, TodoRead, TodoWithTagsRead

configure_logging()
app = FastAPI(title=settings.app_name)
logger = logging.getLogger("app.todos")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()


@app.middleware("http")
async def observability_middleware(request, call_next):
    return await record_request_metrics(request, call_next)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.get("/todos", response_model=list[TodoRead] | list[TodoWithTagsRead])
async def list_todos(
    request: Request,
    search: str | None = Query(default=None, min_length=1, max_length=120),
    search_mode: str = Query(default="all", pattern="^(all|contains|exact)$"),
    include_tags: bool = Query(default=False),
    tag_load_strategy: str = Query(default="n_plus_one", pattern="^(n_plus_one|selectin)$"),
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
    cached_todos = get_todo_list_cache() if use_cache else None
    if cached_todos is not None:
        logger.info(
            "todos served from cache",
            extra={
                "event": "list_todos",
                "extra_fields": {
                    "todo_count": len(cached_todos),
                    "cache_status": "hit",
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

    request.state.response_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    if use_cache:
        set_todo_list_cache(payload)
    logger.info(
        "todos listed",
        extra={
            "event": "list_todos",
            "extra_fields": {
                "todo_count": len(todos),
                "cache_status": "miss" if use_cache else "bypass",
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
