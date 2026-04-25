from __future__ import annotations

import sys

from app.db import SessionLocal, fk_index_audit_rows


def main() -> int:
    db = SessionLocal()
    try:
        rows = fk_index_audit_rows(db)
    finally:
        db.close()

    if not rows:
        print("No missing foreign key indexes found.")
        return 0

    print("Missing foreign key indexes detected:")
    for row in rows:
        print(
            f"- {row['table_name']}.{', '.join(row['column_names'])}: {row['fix_statement']}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
