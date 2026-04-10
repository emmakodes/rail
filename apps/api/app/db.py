from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.observability import increment_db_query_count


engine = create_engine(settings.normalized_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_todos_title ON todos (title)",
    "CREATE INDEX IF NOT EXISTS ix_todo_tags_todo_id ON todo_tags (todo_id)",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS ix_todos_title_trgm ON todos USING gin (title gin_trgm_ops)",
)


@event.listens_for(engine, "before_cursor_execute")
def count_queries(*_args, **_kwargs) -> None:
    increment_db_query_count()


def initialize_database() -> None:
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for statement in INDEX_STATEMENTS:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
