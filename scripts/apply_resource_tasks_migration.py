"""Apply the resource task tables migration to the configured Postgres database."""
from __future__ import annotations

from pathlib import Path

import psycopg

from content_factory.db import default_database_target


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    migration = (ROOT / "apps" / "web" / "drizzle" / "0002_resource_tasks.sql").read_text(encoding="utf-8")
    migration = migration.replace("--> statement-breakpoint", "")
    with psycopg.connect(default_database_target()) as conn:
        conn.execute(migration)
        conn.commit()
        rows = conn.execute(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
              and table_name in ('resource_tasks', 'resource_task_logs')
            order by table_name
            """
        ).fetchall()
    print(rows)


if __name__ == "__main__":
    main()
