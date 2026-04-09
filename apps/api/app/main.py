import logging
import time
import asyncio

import httpx
from fastapi import Depends, FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.cache import get_todo_list_cache, invalidate_todo_list_cache, set_todo_list_cache
from app.config import settings
from app.db import engine, get_db
from app.models import Base, Todo
from app.observability import configure_logging, metrics_response, record_request_metrics
from app.schemas import TodoCreate, TodoRead

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
    Base.metadata.create_all(bind=engine)


@app.middleware("http")
async def observability_middleware(request, call_next):
    return await record_request_metrics(request, call_next)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.get("/todos", response_model=list[TodoRead])
async def list_todos(db: Session = Depends(get_db)) -> list[Todo] | list[dict]:
    cached_todos = get_todo_list_cache()
    if cached_todos is not None:
        logger.info(
            "todos served from cache",
            extra={
                "event": "list_todos",
                "extra_fields": {
                    "todo_count": len(cached_todos),
                    "cache_status": "hit",
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

    todos = db.query(Todo).order_by(Todo.id.desc()).all()
    payload = jsonable_encoder(todos)
    set_todo_list_cache(payload)
    logger.info(
        "todos listed",
        extra={
            "event": "list_todos",
            "extra_fields": {
                "todo_count": len(todos),
                "cache_status": "miss",
                "delay_seconds": settings.todo_read_delay_seconds,
            },
        },
    )
    return payload


@app.post("/todos", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoCreate, db: Session = Depends(get_db)) -> Todo:
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
