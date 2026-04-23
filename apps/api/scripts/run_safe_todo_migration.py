from __future__ import annotations

import time

from sqlalchemy import create_engine, text

from app.config import settings


def lock_timeout_sql(seconds: float) -> str:
    return f"{max(seconds, 0.001):.3f}s"


def backfill_batch(engine, batch_size: int) -> int:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                WITH batch AS (
                    SELECT id
                    FROM todos
                    WHERE migration_status IS NULL
                    ORDER BY id
                    LIMIT :batch_size
                )
                UPDATE todos
                SET migration_status = 'legacy'
                WHERE id IN (SELECT id FROM batch)
                RETURNING id
                """
            ),
            {"batch_size": batch_size},
        ).fetchall()
    return len(rows)


def main() -> None:
    engine = create_engine(settings.normalized_database_url, pool_pre_ping=True)
    lock_timeout = lock_timeout_sql(settings.migration_lock_timeout_seconds)

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
        connection.execute(text("ALTER TABLE todos ADD COLUMN IF NOT EXISTS migration_status TEXT"))

    while True:
        updated = backfill_batch(engine, settings.migration_backfill_batch_size)
        if updated == 0:
            break
        if settings.migration_backfill_pause_seconds > 0:
            time.sleep(settings.migration_backfill_pause_seconds)

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
        connection.execute(text("ALTER TABLE todos ALTER COLUMN migration_status SET DEFAULT 'legacy'"))
        constraint_exists = connection.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'todos_migration_status_not_null'
                """
            )
        ).scalar()
        if not constraint_exists:
            connection.execute(
                text(
                    """
                    ALTER TABLE todos
                    ADD CONSTRAINT todos_migration_status_not_null
                    CHECK (migration_status IS NOT NULL) NOT VALID
                    """
                )
            )

    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL lock_timeout = '{lock_timeout}'"))
        connection.execute(text("ALTER TABLE todos VALIDATE CONSTRAINT todos_migration_status_not_null"))

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f"SET lock_timeout = '{lock_timeout}'"))
        connection.execute(text("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_todos_migration_status ON todos (migration_status)"))

    print("safe migration completed")


if __name__ == "__main__":
    main()
