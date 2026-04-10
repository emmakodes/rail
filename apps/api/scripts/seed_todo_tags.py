from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Todo, TodoTag


TAGS = ["work", "urgent", "home", "admin"]


def seed_tags(db: Session, limit: int, tags_per_todo: int) -> None:
    todos = db.query(Todo).order_by(Todo.id.asc()).limit(limit).all()
    print(f"found {len(todos)} todos to tag")

    for todo in todos:
        if todo.tags:
            continue
        for index in range(tags_per_todo):
            db.add(TodoTag(todo_id=todo.id, label=TAGS[index % len(TAGS)]))
    db.commit()
    print("todo tags seeded")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--tags-per-todo", type=int, default=4)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_tags(db, limit=args.limit, tags_per_todo=args.tags_per_todo)
    finally:
        db.close()


if __name__ == "__main__":
    main()
