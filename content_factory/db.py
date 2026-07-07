"""Database helpers for ContentPilot execution tasks.

Drizzle owns the schema and migrations. Python task code connects to the same
Postgres database by default; the HTTP SQL bridge is kept only as an explicit
legacy transition path.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL_ENV = "CONTENTPILOT_DATABASE_URL"
LEGACY_DATABASE_URL_ENV = "CONTENT_FACTORY_DATABASE_URL"
DATABASE_API_URL_ENV = "CONTENTPILOT_DATABASE_API_URL"
LEGACY_DATABASE_API_URL_ENV = "CONTENT_FACTORY_DATABASE_API_URL"
DEFAULT_POSTGRES_URL = "postgresql://postgres:Postgres2024%40%23@192.168.0.46:5433/contentpilot"
RUNTIME_SETTINGS_FILE = ROOT / "data" / "runtime-settings.json"


def _database_url_from_runtime_settings() -> str | None:
    try:
        data = json.loads(RUNTIME_SETTINGS_FILE.read_text(encoding="utf-8"))
        settings = data.get("database") or {}
        host = settings["host"]
        port = int(settings["port"])
        database = settings["database"]
        user = settings["user"]
        password = settings.get("password", "")
    except Exception:
        return None

    from urllib.parse import quote

    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{database}"


def default_database_target() -> str:
    return (
        _database_url_from_runtime_settings()
        or os.environ.get(DATABASE_URL_ENV)
        or os.environ.get(LEGACY_DATABASE_URL_ENV)
        or DEFAULT_POSTGRES_URL
    )


def is_postgres_target(target: str | Path) -> bool:
    target_str = str(target)
    return target_str.startswith(("postgres://", "postgresql://"))


def pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(item)) for item in vector) + "]"


def _convert_named_placeholders(sql: str, params: Any) -> tuple[str, list[Any]]:
    if not isinstance(params, dict):
        return sql, list(params) if params is not None else []

    pattern = re.compile(r"%\(([^)]+)\)s")
    matches = pattern.findall(sql)
    if not matches:
        return sql, []

    positional_params = [params[match] for match in matches]
    return pattern.sub("?", sql), positional_params


def _convert_qmark_placeholders(sql: str) -> str:
    return sql.replace("?", "%s")


def _translate_sqlite_insert(sql: str) -> str:
    translated = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.IGNORECASE)
    translated = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", translated, flags=re.IGNORECASE)
    upper = translated.upper()

    conflict_targets = {
        "CRAWL_SITES": "(base_url)",
        "CRAWL_URLS": "(site_id, url_hash)",
        "TOPIC_POOL": "(id)",
        "RESEARCH_ASSETS": "(topic_id, url)",
        "CRAWL_SITEMAPS": "(site_id, sitemap_url)",
        "CRAWL_PAGES": "(site_id, url)",
        "CRAWL_PAGE_EMBEDDINGS": "(page_id, source_field, model)",
        "CONTENT_ITEMS": "(id)",
        "PUBLICATION_RECORDS": "(id)",
        "REVIEW_RECORDS": "(id)",
        "PERFORMANCE_METRICS": "(id)",
        "SCHEMA_MIGRATIONS": "(version)",
    }
    if " ON CONFLICT " in upper:
        return translated
    for table, target in conflict_targets.items():
        if f"INSERT INTO {table}" in upper:
            return f"{translated} ON CONFLICT {target} DO NOTHING"
    return translated


def _prepare_postgres_sql(sql: str) -> str:
    return _convert_qmark_placeholders(_translate_sqlite_insert(sql))


class ApiCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row_count: int = 0):
        self.rows = rows or []
        self.rowcount = row_count
        self.index = 0

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        if self.index < len(self.rows):
            row = self.rows[self.index]
            self.index += 1
            return row
        return None

    def __iter__(self):
        return iter(self.rows)


class ApiDatabase:
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.backend = "api"

    def execute(self, sql: str, params: Any = ()) -> ApiCursor:
        query_sql, query_params = _convert_named_placeholders(sql, params)
        payload = {"sql": query_sql, "params": query_params}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        token = os.environ.get("CONTENTPILOT_DB_QUERY_TOKEN") or os.environ.get("CONTENTPILOT_ADMIN_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                data = json.loads(res.read().decode("utf-8"))
                if "error" in data:
                    raise RuntimeError(data["error"])
                return ApiCursor(data.get("rows", []), data.get("rowCount", 0))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_msg = json.loads(err_body).get("error", err_body)
            except Exception:
                err_msg = err_body
            raise RuntimeError(f"Database HTTP Error: {err_msg}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to query database API: {exc}") from exc

    def executescript(self, schema: str) -> None:
        for statement in schema.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self) -> "ApiDatabase":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass


class PostgresDatabase:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.backend = "postgres"
        self.conn = psycopg.connect(database_url, row_factory=dict_row, autocommit=True)

    def execute(self, sql: str, params: Any = ()) -> ApiCursor:
        query_sql = _prepare_postgres_sql(sql)
        query_params = params if params is not None else ()
        with self.conn.cursor() as cur:
            cur.execute(query_sql, query_params)
            rows = cur.fetchall() if cur.description else []
            return ApiCursor([dict(row) for row in rows], cur.rowcount)

    def executescript(self, schema: str) -> None:
        statements = [statement.strip() for statement in schema.split(";") if statement.strip()]
        with self.conn.cursor() as cur:
            for statement in statements:
                cur.execute(_prepare_postgres_sql(statement))

    def commit(self) -> None:
        pass

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "PostgresDatabase":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


Database = PostgresDatabase | ApiDatabase


def _explicit_api_url() -> str | None:
    return os.environ.get(DATABASE_API_URL_ENV) or os.environ.get(LEGACY_DATABASE_API_URL_ENV)


def connect(target: str | Path | None = None) -> Database:
    target_str = str(target or default_database_target())
    api_url = _explicit_api_url()
    if target_str.startswith(("http://", "https://")):
        api_url = target_str
    if api_url:
        return ApiDatabase(api_url)

    if not is_postgres_target(target_str):
        raise ValueError(
            f"Unsupported database target: {target_str}. "
            "Use CONTENTPILOT_DATABASE_URL for Postgres, or set CONTENTPILOT_DATABASE_API_URL explicitly for the legacy SQL bridge."
        )

    return PostgresDatabase(target_str)
