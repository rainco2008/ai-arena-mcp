"""Initialize the SQLite database used by the content factory MVP."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "content_factory.sqlite"
DEFAULT_SCHEMA_PATH = ROOT / "sql" / "content_factory_schema.sql"


def init_db(db_path: Path, schema_path: Path) -> None:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = schema_path.read_text(encoding="utf-8")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema)
        conn.commit()


def inspect_db(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize content factory SQLite database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH, help="Schema SQL path.")
    args = parser.parse_args()

    db_path = args.db.resolve()
    schema_path = args.schema.resolve()
    init_db(db_path, schema_path)
    tables = inspect_db(db_path)

    print(f"Initialized database: {db_path}")
    print("Tables:")
    for table in tables:
        print(f"- {table}")


if __name__ == "__main__":
    main()
