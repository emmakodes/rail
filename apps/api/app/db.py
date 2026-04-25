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

FK_INDEX_AUDIT_QUERY = """
WITH fk AS (
    SELECT
        c.oid AS constraint_oid,
        c.conname AS constraint_name,
        n.nspname AS schema_name,
        rel.relname AS table_name,
        c.conrelid,
        frel.relname AS referenced_table_name,
        c.conkey,
        array_agg(att.attname ORDER BY cols.ordinality) AS column_names
    FROM pg_constraint c
    JOIN pg_class rel ON rel.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = rel.relnamespace
    JOIN pg_class frel ON frel.oid = c.confrelid
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS cols(attnum, ordinality) ON TRUE
    JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = cols.attnum
    WHERE c.contype = 'f'
      AND n.nspname = current_schema()
    GROUP BY c.oid, c.conname, n.nspname, rel.relname, c.conrelid, frel.relname, c.conkey
),
missing AS (
    SELECT
        fk.*,
        NOT EXISTS (
            SELECT 1
            FROM pg_index idx
            WHERE idx.indrelid = fk.conrelid
              AND idx.indisvalid
              AND idx.indpred IS NULL
              AND (idx.indkey::smallint[])[1:array_length(fk.conkey, 1)] = fk.conkey
        ) AS missing_index
    FROM fk
)
SELECT
    schema_name,
    table_name,
    constraint_name,
    column_names,
    referenced_table_name,
    'CREATE INDEX CONCURRENTLY IF NOT EXISTS '
    || 'ix_' || table_name || '_' || array_to_string(column_names, '_')
    || ' ON ' || quote_ident(schema_name) || '.' || quote_ident(table_name)
    || ' (' || array_to_string(ARRAY(SELECT quote_ident(col) FROM unnest(column_names) AS col), ', ') || ');'
    AS fix_statement
FROM missing
WHERE missing_index
ORDER BY table_name, constraint_name
"""


def ensure_fk_index_challenge_schema() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        connection.execute(text("ALTER TABLE todos ADD COLUMN IF NOT EXISTS user_id BIGINT"))
        connection.execute(text("ALTER TABLE todos ADD COLUMN IF NOT EXISTS completed BOOLEAN NOT NULL DEFAULT false"))

        constraint_exists = connection.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_todos_user_id'
                """
            )
        ).scalar()
        if not constraint_exists:
            connection.execute(
                text(
                    """
                    ALTER TABLE todos
                    ADD CONSTRAINT fk_todos_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    """
                )
            )


def fk_index_audit_rows(db: Session) -> list[dict[str, object]]:
    return [dict(row) for row in db.execute(text(FK_INDEX_AUDIT_QUERY)).mappings().all()]


def initialize_database() -> None:
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    ensure_fk_index_challenge_schema()
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
