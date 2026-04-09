from __future__ import annotations

import argparse
import random

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Todo


WORDS = [
    "work",
    "home",
    "gym",
    "email",
    "budget",
    "meeting",
    "deploy",
    "review",
    "report",
    "plan",
]


def build_title(index: int) -> str:
    primary = random.choice(WORDS)
    secondary = random.choice(WORDS)
    if index % 8 == 0:
        return f"{primary} work item {index}"
    return f"{primary} {secondary} task {index}"


def seed_todos(db: Session, total: int, batch_size: int) -> None:
    created = 0
    while created < total:
        batch = []
        remaining = min(batch_size, total - created)
        for offset in range(remaining):
            batch.append(Todo(title=build_title(created + offset + 1)))
        db.bulk_save_objects(batch)
        db.commit()
        created += remaining
        print(f"seeded {created}/{total} todos")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=5_000)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_todos(db, total=args.count, batch_size=args.batch_size)
    finally:
        db.close()


if __name__ == "__main__":
    main()
