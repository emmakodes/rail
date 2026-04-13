from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


engine = create_engine(
    settings.normalized_database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_todos_title ON todos (title)",
    "CREATE INDEX IF NOT EXISTS ix_todo_tags_todo_id ON todo_tags (todo_id)",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS ix_todos_title_trgm ON todos USING gin (title gin_trgm_ops)",
)


def initialize_database() -> None:
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for statement in INDEX_STATEMENTS:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    db.info["query_count"] = 0
    try:
        yield db
    finally:
        db.close()


def pool_snapshot() -> dict[str, str | int | float]:
    checked_out = getattr(engine.pool, "checkedout", lambda: 0)()
    overflow = getattr(engine.pool, "overflow", lambda: 0)()
    return {
        "status": engine.pool.status(),
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout_seconds": settings.db_pool_timeout_seconds,
        "checked_out": checked_out,
        "overflow": overflow,
    }
