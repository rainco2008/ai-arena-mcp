"""Index and search workflows from the Zie619/n8n-workflows repository."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "vendor" / "n8n-workflows" / "workflows"
DEFAULT_INDEX = ROOT / "workflows" / "template-index" / "zie619-n8n-workflows.index.json"


def iter_json_files(source: Path) -> list[Path]:
    return sorted(path for path in source.rglob("*.json") if path.is_file())


def node_type(node: dict[str, Any]) -> str:
    value = node.get("type") or ""
    return str(value)


def infer_triggers(nodes: list[dict[str, Any]]) -> list[str]:
    triggers = []
    for node in nodes:
        value = node_type(node).lower()
        name = str(node.get("name") or "").lower()
        if "trigger" in value or "trigger" in name or "webhook" in value or "cron" in value or "schedule" in value:
            triggers.append(node_type(node) or str(node.get("name") or "unknown"))
    return sorted(set(triggers))


def load_workflow(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return None
    return data


def build_index(source: Path, index_path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for path in iter_json_files(source):
        workflow = load_workflow(path)
        if not workflow:
            continue
        nodes = [node for node in workflow.get("nodes", []) if isinstance(node, dict)]
        node_types = sorted(set(filter(None, (node_type(node) for node in nodes))))
        relative = path.relative_to(ROOT).as_posix()
        category = path.parent.name
        text = " ".join(
            [
                str(workflow.get("name") or path.stem),
                category,
                " ".join(node_types),
                " ".join(str(node.get("name") or "") for node in nodes),
            ]
        ).lower()
        records.append(
            {
                "id": path.stem,
                "name": workflow.get("name") or path.stem,
                "path": relative,
                "category": category,
                "node_count": len(nodes),
                "node_types": node_types,
                "triggers": infer_triggers(nodes),
                "search_text": text,
            }
        )
    payload = {
        "source": "https://github.com/Zie619/n8n-workflows",
        "source_path": source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else str(source),
        "workflow_count": len(records),
        "records": records,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def search_index(index_path: Path, query: str, limit: int) -> dict[str, Any]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    terms = [term.lower() for term in query.split() if term.strip()]
    scored = []
    for record in payload.get("records", []):
        search_text = record.get("search_text", "")
        score = sum(search_text.count(term) for term in terms)
        if score > 0:
            item = {key: value for key, value in record.items() if key != "search_text"}
            item["score"] = score
            scored.append(item)
    scored.sort(key=lambda item: (-item["score"], item["node_count"], item["name"]))
    return {"ok": True, "query": query, "count": len(scored), "results": scored[:limit]}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Index/search Zie619 n8n workflow templates")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    source = Path(args.source)
    index_path = Path(args.index)
    if args.query:
        if not index_path.exists():
            build_index(source, index_path)
        result = search_index(index_path, args.query, args.limit)
    else:
        payload = build_index(source, index_path)
        result = {"ok": True, "index": str(index_path), "workflow_count": payload["workflow_count"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
