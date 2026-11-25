#!/usr/bin/env python3
"""
One-off migration: add env_vars and interrupt_payload columns to build_runs table.
Run with: python scripts/migrate_add_hitl_columns.py

Safe to run multiple times (checks if columns exist first).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.database import engine


def column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def main():
    with engine.connect() as conn:
        if not column_exists(conn, "build_runs", "env_vars"):
            conn.execute(text("ALTER TABLE build_runs ADD COLUMN env_vars JSONB"))
            print("✓ Added env_vars column")
        else:
            print("⚠ env_vars already exists — skipping")

        if not column_exists(conn, "build_runs", "interrupt_payload"):
            conn.execute(text("ALTER TABLE build_runs ADD COLUMN interrupt_payload JSONB"))
            print("✓ Added interrupt_payload column")
        else:
            print("⚠ interrupt_payload already exists — skipping")

        conn.commit()
        print("✓ Migration complete")


if __name__ == "__main__":
    main()
