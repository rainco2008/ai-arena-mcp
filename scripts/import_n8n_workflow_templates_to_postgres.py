"""Import Zie619/n8n-workflows templates into Postgres for workflow design reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.db import connect, default_database_target

DEFAULT_SOURCE = ROOT / "vendor" / "n8n-workflows" / "workflows"
SOURCE_REPO = "https://github.com/Zie619/n8n-workflows"


def iter_json_files(source: Path) -> list[Path]:
    return sorted(path for path in source.rglob("*.json") if path.is_file())


def load_workflow(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return None
    return data


def node_type(node: dict[str, Any]) -> str:
    return str(node.get("type") or "")


def infer_triggers(nodes: list[dict[str, Any]]) -> list[str]:
    triggers: list[str] = []
    for node in nodes:
        value = node_type(node).lower()
        name = str(node.get("name") or "").lower()
        if "trigger" in value or "trigger" in name or "webhook" in value or "cron" in value or "schedule" in value:
            triggers.append(node_type(node) or str(node.get("name") or "unknown"))
    return sorted(set(triggers))


def workflow_record(path: Path, workflow: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in workflow.get("nodes", []) if isinstance(node, dict)]
    node_types = sorted(set(filter(None, (node_type(node) for node in nodes))))
    relative_path = path.relative_to(ROOT).as_posix()
    category = path.parent.name
    name = str(workflow.get("name") or path.stem)
    search_text = " ".join(
        [
            name,
            category,
            " ".join(node_types),
            " ".join(str(node.get("name") or "") for node in nodes),
        ]
    ).lower()
    raw = json.dumps(workflow, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "id": hashlib.sha256(f"{SOURCE_REPO}:{relative_path}".encode("utf-8")).hexdigest(),
        "source_repo": SOURCE_REPO,
        "source_path": relative_path,
        "category": category,
        "name": name,
        "node_count": len(nodes),
        "node_types": node_types,
        "triggers": infer_triggers(nodes),
        "search_text": search_text,
        "workflow_json": workflow,
        "workflow_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def ensure_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS n8n_workflow_templates (
          id TEXT PRIMARY KEY,
          source_repo TEXT NOT NULL,
          source_path TEXT NOT NULL UNIQUE,
          category TEXT,
          name TEXT NOT NULL,
          node_count INTEGER NOT NULL DEFAULT 0,
          node_types JSONB NOT NULL DEFAULT '[]'::jsonb,
          triggers JSONB NOT NULL DEFAULT '[]'::jsonb,
          search_text TEXT NOT NULL,
          workflow_json JSONB NOT NULL,
          workflow_hash TEXT NOT NULL,
          imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_n8n_workflow_templates_category ON n8n_workflow_templates(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_n8n_workflow_templates_node_count ON n8n_workflow_templates(node_count)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_n8n_workflow_templates_search ON n8n_workflow_templates USING gin(to_tsvector('simple', search_text))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_n8n_workflow_templates_workflow_json ON n8n_workflow_templates USING gin(workflow_json)")


def import_templates(conn: Any, source: Path) -> dict[str, Any]:
    inserted_or_updated = 0
    skipped = 0
    categories: dict[str, int] = {}
    sql = """
        INSERT INTO n8n_workflow_templates
          (id, source_repo, source_path, category, name, node_count, node_types, triggers,
           search_text, workflow_json, workflow_hash)
        VALUES
          (%(id)s, %(source_repo)s, %(source_path)s, %(category)s, %(name)s, %(node_count)s,
           %(node_types)s, %(triggers)s, %(search_text)s, %(workflow_json)s, %(workflow_hash)s)
        ON CONFLICT (source_path) DO UPDATE SET
          source_repo = EXCLUDED.source_repo,
          category = EXCLUDED.category,
          name = EXCLUDED.name,
          node_count = EXCLUDED.node_count,
          node_types = EXCLUDED.node_types,
          triggers = EXCLUDED.triggers,
          search_text = EXCLUDED.search_text,
          workflow_json = EXCLUDED.workflow_json,
          workflow_hash = EXCLUDED.workflow_hash,
          updated_at = now()
    """
    for path in iter_json_files(source):
        workflow = load_workflow(path)
        if not workflow:
            skipped += 1
            continue
        record = workflow_record(path, workflow)
        record["node_types"] = json.dumps(record["node_types"], ensure_ascii=False)
        record["triggers"] = json.dumps(record["triggers"], ensure_ascii=False)
        record["workflow_json"] = json.dumps(record["workflow_json"], ensure_ascii=False)
        conn.execute(sql, record)
        inserted_or_updated += 1
        categories[record["category"]] = categories.get(record["category"], 0) + 1
    return {"imported": inserted_or_updated, "skipped": skipped, "categories": categories}


def sample_queries(conn: Any) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) AS n FROM n8n_workflow_templates").fetchone()["n"]
    categories = conn.execute(
        """
        SELECT category, COUNT(*) AS n
        FROM n8n_workflow_templates
        GROUP BY category
        ORDER BY n DESC, category
        LIMIT 10
        """
    ).fetchall()
    examples = conn.execute(
        """
        SELECT name, category, node_count, source_path
        FROM n8n_workflow_templates
        WHERE to_tsvector('simple', search_text) @@ plainto_tsquery('simple', %s)
        ORDER BY node_count ASC, name ASC
        LIMIT 5
        """,
        ("webhook slack approval",),
    ).fetchall()
    return {"total": total, "top_categories": [dict(row) for row in categories], "sample_search": [dict(row) for row in examples]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Zie619 n8n workflow templates into Postgres.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Source workflow template directory.")
    parser.add_argument("--postgres", default=default_database_target(), help="Destination Postgres URL.")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise FileNotFoundError(f"Template source not found: {source}")

    with connect(args.postgres) as conn:
        ensure_schema(conn)
        report = import_templates(conn, source)
        conn.commit()
        verification = sample_queries(conn)

    print(json.dumps({"ok": True, "source": str(source), "report": report, "verification": verification}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
