from __future__ import annotations

import argparse

from sqlalchemy import text

from app.db import engine, ensure_fk_index_challenge_schema


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=10_000)
    args = parser.parse_args()

    ensure_fk_index_challenge_schema()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (name, email)
                SELECT
                    'User ' || series_id,
                    'user' || series_id || '@example.com'
                FROM generate_series(1, :user_count) AS series_id
                ON CONFLICT (email) DO NOTHING
                """
            ),
            {"user_count": args.users},
        )
        connection.execute(
            text(
                """
                UPDATE todos
                SET
                    user_id = ((id - 1) % :user_count) + 1,
                    completed = (mod(id, 5) = 0)
                WHERE user_id IS NULL
                   OR completed IS DISTINCT FROM (mod(id, 5) = 0)
                """
            ),
            {"user_count": args.users},
        )
        totals = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM users) AS users_total,
                    (SELECT count(*) FROM todos WHERE user_id IS NOT NULL) AS assigned_todos
                """
            )
        ).mappings().one()

    print(
        f"users_total={totals['users_total']} assigned_todos={totals['assigned_todos']}"
    )


if __name__ == "__main__":
    main()
