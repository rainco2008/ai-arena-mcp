"""Initialize the content factory database using Drizzle push."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.db import connect, default_database_target


def ensure_pgvector(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()


def init_db(database_url: str) -> None:
    print("Ensuring pgvector extension exists...")
    ensure_pgvector(database_url)
    print("Running Drizzle Kit db:push to synchronize database schemas...")
    env = os.environ.copy()
    env["CONTENTPILOT_DATABASE_URL"] = database_url
    subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "db:push", "--", "--force"], cwd=ROOT, check=True, env=env)


def inspect_db(database_url: str) -> list[str]:
    try:
        with connect(database_url) as conn:
            rows = conn.execute(
                """
                SELECT table_name AS name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            ).fetchall()
        return [row["name"] if isinstance(row, dict) else row[0] for row in rows]
    except Exception as exc:
        print(f"Note: Could not inspect tables (Next.js server might not be running yet): {exc}")
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize content factory database.")
    parser.add_argument("--db", default=default_database_target(), help="Postgres database URL.")
    args = parser.parse_args()

    init_db(args.db)
    tables = inspect_db(args.db)

    print("\nDatabase initialization complete.")
    if tables:
        print("Tables:")
        for table in tables:
            print(f"- {table}")


if __name__ == "__main__":
    main()
