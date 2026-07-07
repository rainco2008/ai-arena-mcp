"""Migrate ContentPilot data from the local SQLite MVP database to Postgres."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.db import default_database_target

DEFAULT_SQLITE_DB = ROOT / "data" / "content_factory.sqlite"

TABLES = [
    "schema_migrations",
    "topic_pool",
    "research_assets",
    "content_items",
    "review_records",
    "performance_metrics",
    "publication_records",
    "crawl_sites",
    "crawl_runs",
    "crawl_sitemaps",
    "crawl_urls",
    "crawl_pages",
    "crawl_page_embeddings",
]


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]


def postgres_columns(conn: psycopg.Connection[Any], table: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [row["column_name"] for row in rows]


def convert_value(table: str, column: str, value: Any) -> Any:
    if value is None:
        return None
    if table == "crawl_page_embeddings" and column == "vector":
        if isinstance(value, str) and value.startswith("["):
            try:
                vector = json.loads(value)
            except json.JSONDecodeError:
                return value
            return "[" + ",".join(str(float(item)) for item in vector) + "]"
    return value


def conflict_target(table: str, columns: list[str]) -> str:
    unique_targets = {
        "schema_migrations": ["version"],
        "topic_pool": ["id"],
        "research_assets": ["topic_id", "url"],
        "content_items": ["id"],
        "review_records": ["id"],
        "performance_metrics": ["id"],
        "publication_records": ["id"],
        "crawl_sites": ["base_url"],
        "crawl_runs": ["id"],
        "crawl_sitemaps": ["site_id", "sitemap_url"],
        "crawl_urls": ["site_id", "url_hash"],
        "crawl_pages": ["site_id", "url"],
        "crawl_page_embeddings": ["page_id", "source_field", "model"],
    }
    target = unique_targets.get(table, ["id"])
    missing = [column for column in target if column not in columns]
    if missing:
        raise RuntimeError(f"{table} missing conflict columns: {missing}")
    return ", ".join(target)


def migrate_table(src: sqlite3.Connection, dst: psycopg.Connection[Any], table: str) -> dict[str, int]:
    src_cols = sqlite_columns(src, table)
    dst_cols = postgres_columns(dst, table)
    columns = [column for column in src_cols if column in dst_cols]
    if not columns:
        return {"read": 0, "written": 0}

    rows = src.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    if not rows:
        return {"read": 0, "written": 0}

    placeholders = ", ".join(["%s"] * len(columns))
    target = conflict_target(table, columns)
    update_columns = [column for column in columns if column not in target.split(", ")]
    if update_columns:
        assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
        on_conflict = f"ON CONFLICT ({target}) DO UPDATE SET {assignments}"
    else:
        on_conflict = f"ON CONFLICT ({target}) DO NOTHING"
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) {on_conflict}"

    with dst.cursor() as cur:
        for row in rows:
            values = [convert_value(table, column, row[column]) for column in columns]
            cur.execute(sql, values)
    return {"read": len(rows), "written": len(rows)}


def table_counts_sqlite(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] for table in TABLES}


def table_counts_postgres(conn: psycopg.Connection[Any]) -> dict[str, int]:
    return {table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] for table in TABLES}


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate ContentPilot SQLite data to Postgres.")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE_DB), help="Source SQLite database path.")
    parser.add_argument("--postgres", default=default_database_target(), help="Destination Postgres URL.")
    args = parser.parse_args()

    src = sqlite3.connect(args.sqlite)
    src.row_factory = sqlite3.Row
    report: dict[str, dict[str, int]] = {}
    with psycopg.connect(args.postgres, row_factory=dict_row) as dst:
        for table in TABLES:
            report[table] = migrate_table(src, dst, table)
        dst.commit()
        pg_counts = table_counts_postgres(dst)

    print(
        json.dumps(
            {
                "migrated": report,
                "sqlite_counts": table_counts_sqlite(src),
                "postgres_counts": pg_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
