"""Content factory MVP command line tasks for n8n workflows."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "content_factory.sqlite"
DEFAULT_SEARCH_API = os.environ.get("CONTENT_FACTORY_SEARCH_API", "http://127.0.0.1:8080")
DEFAULT_PUBLISH_WEBHOOK = os.environ.get("CONTENT_FACTORY_PUBLISH_WEBHOOK")
DEFAULT_INBOX = ROOT / "data" / "inbox"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def emit(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=True, indent=2))


def http_json(url: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:800]}") from exc
    return json.loads(body) if body else {}


def first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None


def assert_allowed_input_path(path: Path, inbox: Path) -> Path:
    resolved = path.resolve()
    allowed_root = inbox.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Input file not found: {resolved}")
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise RuntimeError(f"Input file must be under inbox directory: {allowed_root}") from exc
    return resolved


def init_db(args: argparse.Namespace) -> None:
    from scripts.init_content_factory_db import init_db

    init_db(Path(args.db), ROOT / "sql" / "content_factory_schema.sql")
    emit({"ok": True, "db": str(Path(args.db).resolve())})


def seed_topic(args: argparse.Namespace) -> None:
    topic_id = args.id or str(uuid.uuid4())
    ts = now()
    with connect(Path(args.db)) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO topic_pool
              (id, keyword, source, intent, priority, status, owner, due_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'new', ?, ?, ?, ?)
            """,
            (topic_id, args.keyword, args.source, args.intent, args.priority, args.owner, args.due_at, ts, ts),
        )
        row = conn.execute("SELECT * FROM topic_pool WHERE id = ?", (topic_id,)).fetchone()
    emit({"ok": True, "topic": dict(row)})


def list_topics(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM topic_pool
            WHERE (? IS NULL OR status = ?)
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            """,
            (args.status, args.status, args.limit),
        ).fetchall()
    emit({"ok": True, "topics": [dict(row) for row in rows]})


def _next_topic(conn: sqlite3.Connection, status: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM topic_pool
        WHERE status = ?
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        """,
        (status,),
    ).fetchone()


def discover(args: argparse.Namespace) -> None:
    """Create topic candidates from configured seed keywords."""
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    created: list[dict[str, Any]] = []
    ts = now()
    with connect(Path(args.db)) as conn:
        for seed in seeds:
            topic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"content-factory-topic:{seed.lower()}"))
            conn.execute(
                """
                INSERT OR IGNORE INTO topic_pool
                  (id, keyword, source, intent, priority, status, created_at, updated_at)
                VALUES (?, ?, 'seed', 'research', ?, 'new', ?, ?)
                """,
                (topic_id, seed, args.priority, ts, ts),
            )
            created.append({"id": topic_id, "keyword": seed})
    emit({"ok": True, "created": created})


def research(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    api = args.search_api.rstrip("/")
    with connect(db_path) as conn:
        topic = _next_topic(conn, "new")
        if not topic:
            emit({"ok": True, "message": "no new topics"})
            return
        conn.execute("UPDATE topic_pool SET status = 'researching', updated_at = ? WHERE id = ?", (now(), topic["id"]))

    query = f"{topic['keyword']} reliable sources latest background"
    try:
        search = http_json(
            f"{api}/v1/chat/completions",
            {"model": "gemini-search", "messages": [{"role": "user", "content": query}]},
            timeout=args.timeout,
        )
        content = search.get("choices", [{}])[0].get("message", {}).get("content", "")
        reliability = 3
    except Exception as exc:
        if not args.allow_offline:
            raise
        content = (
            f"Offline research placeholder for {topic['keyword']}.\n"
            f"Search API was unavailable: {exc}\n"
            "Human review must replace this placeholder with verified sources before publishing."
        )
        reliability = 1

    asset_id = str(uuid.uuid4())
    summary = content[:4000]
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_assets
              (id, topic_id, url, title, summary, quote_safe, reliability, raw_text, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                topic["id"],
                f"search://{topic['keyword']}",
                f"Search research pack: {topic['keyword']}",
                summary,
                summary[:500],
                reliability,
                content,
                now(),
            ),
        )
        conn.execute("UPDATE topic_pool SET status = 'drafting', updated_at = ? WHERE id = ?", (now(), topic["id"]))
    emit({"ok": True, "topic_id": topic["id"], "asset_id": asset_id, "summary_chars": len(summary)})


def ingest_document(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    inbox = Path(args.inbox)
    file_path = assert_allowed_input_path(Path(args.file), inbox)
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError("MarkItDown is not installed. Run: pip install 'markitdown[pdf,docx,pptx,xlsx]'") from exc

    with connect(db_path) as conn:
        topic = conn.execute("SELECT * FROM topic_pool WHERE id = ?", (args.topic_id,)).fetchone()
        if not topic:
            raise RuntimeError(f"Topic not found: {args.topic_id}")

    converter = MarkItDown(enable_plugins=False)
    result = converter.convert(str(file_path))
    markdown = getattr(result, "text_content", None) or getattr(result, "markdown", None) or ""
    if not markdown.strip():
        raise RuntimeError(f"MarkItDown returned empty content for: {file_path}")

    asset_id = str(uuid.uuid4())
    source_url = f"file://{file_path.as_posix()}"
    summary = markdown[:4000]
    ts = now()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_assets
              (id, topic_id, url, title, summary, quote_safe, reliability, raw_text, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                args.topic_id,
                source_url,
                args.title or file_path.name,
                summary,
                summary[:500],
                args.reliability,
                markdown,
                ts,
            ),
        )
        if args.advance_status:
            conn.execute(
                "UPDATE topic_pool SET status = 'drafting', updated_at = ? WHERE id = ? AND status IN ('new', 'researching')",
                (ts, args.topic_id),
            )
    emit(
        {
            "ok": True,
            "topic_id": args.topic_id,
            "asset_id": asset_id,
            "file": str(file_path),
            "markdown_chars": len(markdown),
        }
    )


def draft(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        topic = _next_topic(conn, "drafting")
        if not topic:
            emit({"ok": True, "message": "no topics ready for drafting"})
            return
        assets = conn.execute(
            "SELECT * FROM research_assets WHERE topic_id = ? ORDER BY collected_at DESC",
            (topic["id"],),
        ).fetchall()
        context = "\n\n".join(row["summary"] or "" for row in assets)
        outline = (
            f"1. 背景与读者问题\n"
            f"2. {topic['keyword']} 的核心事实\n"
            f"3. 可执行建议\n"
            f"4. 风险、限制与下一步\n"
        )
        draft_text = (
            f"# {topic['keyword']}\n\n"
            f"## 大纲\n{outline}\n"
            f"## 初稿\n"
            f"围绕“{topic['keyword']}”，本文先解释背景，再整理可靠来源中的关键事实，"
            f"最后给出可执行建议。以下素材来自自动研究包，发布前需要人工复核事实和来源。\n\n"
            f"## 素材摘要\n{context[:6000]}\n"
        )
        content_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO content_items
              (id, topic_id, channel, outline, draft, final, seo_title, meta_description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, 'reviewing', ?, ?)
            """,
            (
                content_id,
                topic["id"],
                args.channel,
                outline,
                draft_text,
                str(topic["keyword"])[:70],
                f"围绕 {topic['keyword']} 的自动研究与内容初稿。",
                now(),
                now(),
            ),
        )
        conn.execute("UPDATE topic_pool SET status = 'reviewing', updated_at = ? WHERE id = ?", (now(), topic["id"]))
    emit({"ok": True, "topic_id": topic["id"], "content_id": content_id})


def quality_gate(args: argparse.Namespace) -> None:
    checked: list[dict[str, Any]] = []
    with connect(Path(args.db)) as conn:
        rows = conn.execute(
            "SELECT * FROM content_items WHERE status = 'reviewing' ORDER BY created_at ASC LIMIT ?",
            (args.limit,),
        ).fetchall()
        for row in rows:
            draft_text = row["draft"] or ""
            checklist = {
                "has_draft": bool(draft_text.strip()),
                "has_outline": bool((row["outline"] or "").strip()),
                "has_seo_title": bool((row["seo_title"] or "").strip()),
                "requires_human_fact_check": True,
                "min_length_ok": len(draft_text) >= args.min_chars,
            }
            decision = (
                "approve"
                if all([checklist["has_draft"], checklist["has_outline"], checklist["has_seo_title"], checklist["min_length_ok"]])
                else "request_changes"
            )
            conn.execute(
                """
                INSERT INTO review_records
                  (id, content_id, reviewer, checklist, decision, comments, created_at)
                VALUES (?, ?, 'automated-quality-gate', ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["id"],
                    json.dumps(checklist, ensure_ascii=False),
                    decision,
                    "Automated quality gate complete. Human approval is still required before publishing.",
                    now(),
                ),
            )
            checked.append({"content_id": row["id"], "decision": decision, "checklist": checklist})
    emit({"ok": True, "checked": checked})


def approval_router(args: argparse.Namespace) -> None:
    routed: list[dict[str, Any]] = []
    with connect(Path(args.db)) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.topic_id, c.channel, c.seo_title
            FROM content_items c
            WHERE c.status = 'reviewing'
            ORDER BY c.created_at ASC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        for row in rows:
            routed.append(
                {
                    "content_id": row["id"],
                    "topic_id": row["topic_id"],
                    "channel": row["channel"],
                    "seo_title": row["seo_title"],
                    "review_url": f"http://localhost:5678/workflow/review-placeholder/{row['id']}",
                    "action_required": "human_review",
                }
            )
    emit({"ok": True, "routed": routed})


def publish(args: argparse.Namespace) -> None:
    published: list[dict[str, Any]] = []
    publish_webhook = args.publish_webhook
    with connect(Path(args.db)) as conn:
        rows = conn.execute(
            """
            SELECT c.*
            FROM content_items c
            WHERE c.status = 'reviewing'
              AND EXISTS (
                SELECT 1
                FROM review_records r
                WHERE r.content_id = c.id
                  AND r.decision = 'approve'
              )
            ORDER BY c.created_at ASC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        for row in rows:
            final_text = row["final"] or row["draft"] or ""
            payload = {
                "content_id": row["id"],
                "topic_id": row["topic_id"],
                "channel": row["channel"],
                "title": row["seo_title"],
                "meta_description": row["meta_description"],
                "body": final_text,
            }
            if publish_webhook:
                response = http_json(publish_webhook, payload, timeout=args.timeout)
                publish_url = str(first_present(response, ("url", "link", "permalink", "id")) or publish_webhook)
                status = "published"
            elif args.allow_manual_placeholder:
                publish_url = f"manual://{row['channel']}/{row['id']}"
                response = {"source": "manual-placeholder", "url": publish_url}
                status = "published"
            else:
                raise RuntimeError(
                    "No publish webhook configured. Set CONTENT_FACTORY_PUBLISH_WEBHOOK or pass --allow-manual-placeholder."
                )

            ts = now()
            conn.execute(
                "UPDATE content_items SET status = 'published', final = COALESCE(final, draft), updated_at = ? WHERE id = ?",
                (ts, row["id"]),
            )
            conn.execute(
                "UPDATE topic_pool SET status = 'published', updated_at = ? WHERE id = ?",
                (ts, row["topic_id"]),
            )
            conn.execute(
                """
                INSERT INTO publication_records
                  (id, content_id, channel, status, url, response, published_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    row["id"],
                    row["channel"],
                    status,
                    publish_url,
                    json.dumps(response, ensure_ascii=False),
                    ts,
                    ts,
                ),
            )
            published.append({"content_id": row["id"], "channel": row["channel"], "url": publish_url})
    emit({"ok": True, "published": published})


def metrics_feedback(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        published = conn.execute(
            "SELECT id, channel FROM content_items WHERE status = 'published' LIMIT ?",
            (args.limit,),
        ).fetchall()
        inserted = []
        for row in published:
            metric_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO performance_metrics
                  (id, content_id, channel, impressions, clicks, conversions, engagement, raw_metrics, collected_at)
                VALUES (?, ?, ?, 0, 0, 0, 0, ?, ?)
                """,
                (metric_id, row["id"], row["channel"], json.dumps({"source": "manual-placeholder"}), now()),
            )
            inserted.append(metric_id)
    emit({"ok": True, "inserted": inserted})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Content factory MVP tasks")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=init_db)

    seed = sub.add_parser("seed-topic")
    seed.add_argument("keyword")
    seed.add_argument("--id")
    seed.add_argument("--source", default="manual")
    seed.add_argument("--intent", default="research")
    seed.add_argument("--priority", type=int, default=0)
    seed.add_argument("--owner")
    seed.add_argument("--due-at")
    seed.set_defaults(func=seed_topic)

    list_cmd = sub.add_parser("list-topics")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=list_topics)

    discover_cmd = sub.add_parser("discover")
    discover_cmd.add_argument("--seeds", default="AI内容工厂,n8n自动化,MCP工作流")
    discover_cmd.add_argument("--priority", type=int, default=10)
    discover_cmd.set_defaults(func=discover)

    research_cmd = sub.add_parser("research")
    research_cmd.add_argument("--search-api", default=DEFAULT_SEARCH_API)
    research_cmd.add_argument("--timeout", type=int, default=90)
    research_cmd.add_argument("--allow-offline", action=argparse.BooleanOptionalAction, default=True)
    research_cmd.set_defaults(func=research)

    ingest_cmd = sub.add_parser("ingest-document")
    ingest_cmd.add_argument("--topic-id", required=True)
    ingest_cmd.add_argument("--file", required=True)
    ingest_cmd.add_argument("--title")
    ingest_cmd.add_argument("--inbox", default=str(DEFAULT_INBOX))
    ingest_cmd.add_argument("--reliability", type=int, default=2)
    ingest_cmd.add_argument("--advance-status", action=argparse.BooleanOptionalAction, default=True)
    ingest_cmd.set_defaults(func=ingest_document)

    draft_cmd = sub.add_parser("draft")
    draft_cmd.add_argument("--channel", default="blog")
    draft_cmd.set_defaults(func=draft)

    quality_cmd = sub.add_parser("quality-gate")
    quality_cmd.add_argument("--limit", type=int, default=10)
    quality_cmd.add_argument("--min-chars", type=int, default=500)
    quality_cmd.set_defaults(func=quality_gate)

    approval_cmd = sub.add_parser("approval-router")
    approval_cmd.add_argument("--limit", type=int, default=10)
    approval_cmd.set_defaults(func=approval_router)

    publish_cmd = sub.add_parser("publish")
    publish_cmd.add_argument("--limit", type=int, default=10)
    publish_cmd.add_argument("--publish-webhook", default=DEFAULT_PUBLISH_WEBHOOK)
    publish_cmd.add_argument("--timeout", type=int, default=30)
    publish_cmd.add_argument("--allow-manual-placeholder", action=argparse.BooleanOptionalAction, default=True)
    publish_cmd.set_defaults(func=publish)

    metrics_cmd = sub.add_parser("metrics-feedback")
    metrics_cmd.add_argument("--limit", type=int, default=50)
    metrics_cmd.set_defaults(func=metrics_feedback)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
