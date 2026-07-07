"""Content factory MVP command line tasks for n8n workflows."""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import time
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .db import connect, default_database_target, pgvector_literal


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = default_database_target()
DEFAULT_SEARCH_API = os.environ.get("CONTENT_FACTORY_SEARCH_API", "http://127.0.0.1:8080")
DEFAULT_EMBEDDING_API = os.environ.get("CONTENT_FACTORY_EMBEDDING_API", "http://127.0.0.1:8080/v1/embeddings")
DEFAULT_EMBEDDING_MODEL = os.environ.get("CONTENT_FACTORY_EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_PUBLISH_WEBHOOK = os.environ.get("CONTENT_FACTORY_PUBLISH_WEBHOOK")
DEFAULT_INBOX = ROOT / "data" / "inbox"
USER_AGENT = os.environ.get(
    "CONTENT_FACTORY_USER_AGENT",
    "ContentFactoryCrawler/0.1 (+https://localhost; contact=local)",
)
BINARY_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".pdf", ".zip", ".rar", ".7z",
    ".mp3", ".mp4", ".mov", ".avi", ".wmv", ".woff", ".woff2", ".ttf", ".eot",
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def normalize_base_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise RuntimeError("base_url is required")
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if not parsed.netloc:
        raise RuntimeError(f"Invalid base URL: {value}")
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), "", "", "", "")).rstrip("/")


def normalize_page_url(value: str, base_url: str | None = None) -> str:
    if base_url:
        value = urllib.parse.urljoin(base_url, value)
    value, _fragment = urllib.parse.urldefrag(value.strip())
    parsed = urllib.parse.urlparse(value)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))


def url_domain(value: str) -> str:
    return urllib.parse.urlparse(value).netloc.lower()


def http_get_text(url: str, timeout: int = 30, max_bytes: int = 5_000_000) -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,application/rss+xml,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raw = raw[:max_bytes]
            headers = {key.lower(): value for key, value in res.headers.items()}
            charset = res.headers.get_content_charset() or "utf-8"
            return int(res.status), headers, raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read(min(max_bytes, 200_000))
        charset = exc.headers.get_content_charset() or "utf-8"
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return int(exc.code), headers, raw.decode(charset, errors="replace")


class LinkAndMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.feed_links: list[str] = []
        self.sitemap_links: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.canonical_url: str | None = None
        self.language: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag == "html" and values.get("lang"):
            self.language = values["lang"]
        if tag == "title":
            self.in_title = True
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "link" and values.get("rel", "").lower() == "canonical" and values.get("href"):
            self.canonical_url = values["href"]
        if tag == "link" and values.get("href"):
            rel = values.get("rel", "").lower()
            link_type = values.get("type", "").lower()
            if "alternate" in rel and ("rss" in link_type or "atom" in link_type):
                self.feed_links.append(values["href"])
            if "sitemap" in rel:
                self.sitemap_links.append(values["href"])
        if tag == "meta":
            key = values.get("name") or values.get("property")
            content = values.get("content")
            if key and content:
                self.meta[key.lower()] = content.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data.strip())


def parse_html(html: str, base_url: str) -> tuple[dict[str, str | None], list[str]]:
    parser = LinkAndMetaParser()
    parser.feed(html)
    title = " ".join(part for part in parser.title_parts if part).strip()
    meta = parser.meta
    metadata = {
        "title": title or meta.get("og:title"),
        "meta_description": meta.get("description") or meta.get("og:description"),
        "language": parser.language,
        "canonical_url": normalize_page_url(parser.canonical_url, base_url) if parser.canonical_url else None,
        "author": meta.get("author") or meta.get("article:author"),
        "published_at": meta.get("article:published_time") or meta.get("date") or meta.get("pubdate"),
        "modified_at": meta.get("article:modified_time") or meta.get("last-modified"),
    }
    links = [normalize_page_url(link, base_url) for link in parser.links if link and not link.lower().startswith(("mailto:", "tel:", "javascript:"))]
    metadata["feed_links"] = [normalize_page_url(link, base_url) for link in parser.feed_links]
    metadata["sitemap_links"] = [normalize_page_url(link, base_url) for link in parser.sitemap_links]
    return metadata, links


def classify_feed_or_sitemap(headers: dict[str, str], body: str) -> str:
    content_type = headers.get("content-type", "").lower()
    sample = body[:500].lower()
    if "rss" in content_type or "<rss" in sample:
        return "rss"
    if "atom" in content_type or "<feed" in sample:
        return "atom"
    if "sitemap" in content_type or "<urlset" in sample or "<sitemapindex" in sample:
        return "sitemap"
    return content_type[:60] or "xml"


def detect_anti_bot_signals(
    status: int | None,
    headers: dict[str, str] | None,
    body: str,
    robots_allowed: bool | None,
) -> dict[str, Any]:
    headers = headers or {}
    lower_headers = {key.lower(): value.lower() for key, value in headers.items()}
    sample = body[:200_000].lower()
    blocked_status_codes = [status] if status in {401, 403, 429, 503} else []
    return {
        "cloudflare": any(key.startswith("cf-") for key in lower_headers) or "cloudflare" in lower_headers.get("server", ""),
        "captcha": any(token in sample for token in ("captcha", "hcaptcha", "recaptcha", "turnstile")),
        "rate_limit": status == 429 or any("ratelimit" in key for key in lower_headers),
        "access_denied": any(token in sample for token in ("access denied", "forbidden", "verify you are human")),
        "requires_js": bool(re.search(r"<noscript[^>]*>.*?(enable|requires?).{0,80}javascript", sample, re.I | re.S)),
        "robots_allowed": robots_allowed,
        "blocked_status_codes": blocked_status_codes,
        "server": headers.get("server"),
    }


def html_to_markdown(html: str) -> str:
    try:
        from markdownify import markdownify as markdownify

        return markdownify(html, heading_style="ATX").strip()
    except Exception:
        text = re.sub(r"(?is)<(script|style).*?</\\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()


def summarize_markdown(markdown: str, search_api: str, timeout: int, allow_offline_ai: bool) -> tuple[str, str]:
    text = markdown.strip()
    if not text:
        return "", "empty"
    prompt = (
        "请用中文给下面网页内容生成可用于内容工厂入库的摘要，保留核心事实、人物/机构、时间、结论和可复用观点，"
        "控制在 300 字以内。\n\n" + text[:12000]
    )
    try:
        response = http_json(
            f"{search_api.rstrip('/')}/v1/chat/completions",
            {"model": "gemini-search", "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        summary = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if summary:
            return summary[:3000], "gemini-search"
    except Exception:
        if not allow_offline_ai:
            raise
    return re.sub(r"\s+", " ", text[:1200]).strip(), "deterministic-local"


def embed_text(text: str, embedding_api: str, model: str, timeout: int, allow_offline_ai: bool) -> tuple[list[float], str, str]:
    text = text.strip()
    if text:
        try:
            response = http_json(embedding_api, {"model": model, "input": text[:8000]}, timeout=timeout)
            vector = response.get("data", [{}])[0].get("embedding")
            if isinstance(vector, list) and vector:
                return [float(item) for item in vector], "openai-compatible", model
        except Exception:
            if not allow_offline_ai:
                raise

    buckets = [0.0] * 64
    for word in re.findall(r"[\w\u4e00-\u9fff]+", text.lower()):
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        buckets[digest[0] % len(buckets)] += (digest[1] / 255.0) + 0.01
    norm = sum(value * value for value in buckets) ** 0.5 or 1.0
    return [round(value / norm, 6) for value in buckets], "deterministic-local", "hash-64"


def ensure_crawl_site(conn, base_url: str):
    base_url = normalize_base_url(base_url)
    domain = url_domain(base_url)
    site_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"content-crawl-site:{base_url}"))
    ts = now()
    conn.execute(
        """
        INSERT OR IGNORE INTO crawl_sites
          (id, base_url, domain, name, allowed_domains, crawl_policy, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            site_id,
            base_url,
            domain,
            domain,
            json.dumps([domain], ensure_ascii=False),
            json.dumps({"same_domain_only": True, "respect_robots_sitemaps": True}, ensure_ascii=False),
            ts,
            ts,
        ),
    )
    conn.execute("UPDATE crawl_sites SET updated_at = ? WHERE id = ?", (ts, site_id))
    row = conn.execute("SELECT * FROM crawl_sites WHERE id = ?", (site_id,)).fetchone()
    if not row:
        raise RuntimeError(f"Failed to create crawl site for {base_url}")
    return row


def should_crawl_url(url: str, allowed_domains: set[str]) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in allowed_domains:
        return False
    return Path(parsed.path.lower()).suffix not in BINARY_EXTENSIONS


def parse_sitemap_urls(xml_text: str, sitemap_url: str) -> tuple[list[str], list[str]]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    child_sitemaps: list[str] = []
    page_urls: list[str] = []
    for sitemap in root.findall(".//{*}sitemap"):
        loc = sitemap.findtext("{*}loc")
        if loc:
            child_sitemaps.append(normalize_page_url(loc, sitemap_url))
    for url in root.findall(".//{*}url"):
        loc = url.findtext("{*}loc")
        if loc:
            page_urls.append(normalize_page_url(loc, sitemap_url))
    if not child_sitemaps and not page_urls:
        for link in root.findall(".//{*}link"):
            loc = (link.text or link.attrib.get("href") or "").strip()
            if loc:
                page_urls.append(normalize_page_url(loc, sitemap_url))
    return child_sitemaps, page_urls


def insert_crawl_url(conn: Any, site_id: str, run_id: str, url: str, source: str, priority: int) -> bool:
    normalized = normalize_page_url(url)
    digest = sha256_text(normalized)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO crawl_urls
          (id, site_id, run_id, url, normalized_url, url_hash, source, priority, status, attempts, discovered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?)
        """,
        (str(uuid.uuid4()), site_id, run_id, url, normalized, digest, source, priority, now()),
    )
    return cur.rowcount > 0


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

    init_db(args.db)
    emit({"ok": True, "db": args.db})


def seed_topic(args: argparse.Namespace) -> None:
    topic_id = args.id or str(uuid.uuid4())
    ts = now()
    with connect(args.db) as conn:
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
    with connect(args.db) as conn:
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


def _next_topic(conn: Any, status: str) -> Any:
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
    with connect(args.db) as conn:
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
    db_target = args.db
    api = args.search_api.rstrip("/")
    with connect(db_target) as conn:
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
    with connect(db_target) as conn:
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
    db_target = args.db
    inbox = Path(args.inbox)
    file_path = assert_allowed_input_path(Path(args.file), inbox)
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError("MarkItDown is not installed. Run: pip install 'markitdown[pdf,docx,pptx,xlsx]'") from exc

    with connect(db_target) as conn:
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
    with connect(db_target) as conn:
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
    with connect(args.db) as conn:
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
    with connect(args.db) as conn:
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
    with connect(args.db) as conn:
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
    with connect(args.db) as conn:
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
    with connect(args.db) as conn:
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


def crawl_discover(args: argparse.Namespace) -> None:
    db_target = args.db
    base_url = normalize_base_url(args.base_url)
    sitemap_candidates = [
        urllib.parse.urljoin(base_url + "/", path)
        for path in ("sitemap.xml", "sitemap_index.xml", "sitemap-index.xml", "wp-sitemap.xml", "sitemap-news.xml")
    ]
    feed_candidates = [
        urllib.parse.urljoin(base_url + "/", path)
        for path in ("feed", "feed.xml", "rss", "rss.xml", "atom.xml")
    ]
    with connect(db_target) as conn:
        site = ensure_crawl_site(conn, base_url)
        site_id = site["id"]
        allowed_domains = set(json.loads(site["allowed_domains"]))
        run_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO crawl_runs
              (id, site_id, kind, trigger, status, started_at, discovered_count, queued_count, fetched_count, failed_count)
            VALUES (?, ?, 'discover', ?, 'running', ?, 0, 0, 0, 0)
            """,
            (run_id, site_id, args.trigger, now()),
        )

    sitemaps: list[str] = []
    feeds: list[str] = []
    crawl_methods: set[str] = set()
    robots_found = False
    robots_allowed: bool | None = None
    robots_text = ""
    robots_status: int | None = None
    robots_headers: dict[str, str] = {}
    robots_url = urllib.parse.urljoin(base_url + "/", "robots.txt")
    try:
        status, headers, robots = http_get_text(robots_url, timeout=args.timeout, max_bytes=300_000)
        robots_status = status
        robots_headers = headers
        if 200 <= status < 400:
            robots_found = True
            robots_text = robots
            robots_allowed = True
            for line in robots.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("sitemap:"):
                    crawl_methods.add("robots_sitemap")
                    sitemaps.append(stripped.split(":", 1)[1].strip())
                if stripped.lower().startswith("disallow:"):
                    disallow_path = stripped.split(":", 1)[1].strip()
                    if disallow_path == "/":
                        robots_allowed = False
    except Exception:
        pass
    sitemaps.extend(url for url in sitemap_candidates if url not in sitemaps)
    feeds.extend(url for url in feed_candidates if url not in feeds)

    discovered: set[str] = set()
    homepage_metadata: dict[str, Any] = {}
    homepage_status: int | None = None
    homepage_headers: dict[str, str] = {}
    homepage_html = ""
    if args.include_home_links:
        try:
            homepage_status, homepage_headers, homepage_html = http_get_text(base_url, timeout=args.timeout)
            if 200 <= homepage_status < 400:
                homepage_metadata, _homepage_links = parse_html(homepage_html, base_url)
                sitemaps.extend(url for url in homepage_metadata.get("sitemap_links", []) if url not in sitemaps)
                feeds.extend(url for url in homepage_metadata.get("feed_links", []) if url not in feeds)
        except Exception:
            pass

    sitemap_queue = list(dict.fromkeys(sitemaps + feeds))[: args.max_sitemaps]
    seen_sitemaps: set[str] = set()
    sitemap_rows = 0
    with connect(db_target) as conn:
        while sitemap_queue and len(seen_sitemaps) < args.max_sitemaps and len(discovered) < args.limit:
            sitemap_url = sitemap_queue.pop(0)
            if sitemap_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sitemap_url)
            sitemap_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{site_id}:{sitemap_url}"))
            try:
                status, headers, body = http_get_text(sitemap_url, timeout=args.timeout)
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}")
                source_kind = classify_feed_or_sitemap(headers, body)
                crawl_methods.add("rss" if source_kind in {"rss", "atom"} else "sitemap")
                child_sitemaps, urls = parse_sitemap_urls(body, sitemap_url)
                sitemap_queue.extend(url for url in child_sitemaps if url not in seen_sitemaps)
                sitemap_rows += 1
                accepted = []
                for url in urls:
                    normalized = normalize_page_url(url)
                    if should_crawl_url(normalized, allowed_domains):
                        accepted.append(normalized)
                for url in accepted:
                    if len(discovered) >= args.limit:
                        break
                    discovered.add(url)
                    insert_crawl_url(conn, site_id, run_id, url, "rss" if source_kind in {"rss", "atom"} else "sitemap", 50)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO crawl_sitemaps
                      (id, site_id, sitemap_url, kind, status, url_count, fetched_at, error)
                    VALUES (?, ?, ?, ?, 'fetched', ?, ?, NULL)
                    """,
                    (sitemap_id, site_id, sitemap_url, source_kind, len(accepted), now()),
                )
            except Exception as exc:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO crawl_sitemaps
                      (id, site_id, sitemap_url, kind, status, url_count, fetched_at, error)
                    VALUES (?, ?, ?, 'xml', 'failed', 0, ?, ?)
                    """,
                    (sitemap_id, site_id, sitemap_url, now(), str(exc)[:1000]),
                )

        if args.include_home_links and len(discovered) < args.limit:
            try:
                status = homepage_status
                html = homepage_html
                if 200 <= status < 400:
                    crawl_methods.add("homepage_links")
                    _metadata, links = parse_html(html, base_url)
                    insert_crawl_url(conn, site_id, run_id, base_url, "homepage", 100)
                    discovered.add(base_url)
                    for link in links:
                        if len(discovered) >= args.limit:
                            break
                        if should_crawl_url(link, allowed_domains):
                            discovered.add(link)
                            insert_crawl_url(conn, site_id, run_id, link, "homepage-link", 25)
            except Exception:
                pass

        queued_count = conn.execute(
            "SELECT COUNT(*) FROM crawl_urls WHERE site_id = ? AND status = 'queued'",
            (site_id,),
        ).fetchone()[0]
        ts = now()
        anti_bot_signals = detect_anti_bot_signals(
            homepage_status or robots_status,
            homepage_headers or robots_headers,
            homepage_html or robots_text,
            robots_allowed,
        )
        crawl_policy = {
            "same_domain_only": True,
            "respect_robots_sitemaps": True,
            "crawl_methods": sorted(crawl_methods),
            "robots_txt": {
                "url": robots_url,
                "found": robots_found,
                "status": robots_status,
                "allowed": robots_allowed,
            },
            "sitemap_urls": list(dict.fromkeys(sitemaps)),
            "rss_urls": list(dict.fromkeys(feeds)),
            "anti_bot_signals": anti_bot_signals,
            "homepage": {
                "status": homepage_status,
                "content_type": homepage_headers.get("content-type"),
                "metadata": homepage_metadata,
            },
            "last_discovery": {
                "run_id": run_id,
                "discovered_count": len(discovered),
                "queued_count": queued_count,
                "sitemaps_checked": len(seen_sitemaps),
                "sitemap_rows": sitemap_rows,
                "finished_at": ts,
            },
        }
        conn.execute(
            """
            UPDATE crawl_runs
            SET status = 'succeeded', finished_at = ?, discovered_count = ?, queued_count = ?
            WHERE id = ?
            """,
            (ts, len(discovered), queued_count, run_id),
        )
        conn.execute(
            "UPDATE crawl_sites SET crawl_policy = ?, last_discovered_at = ?, updated_at = ? WHERE id = ?",
            (json.dumps(crawl_policy, ensure_ascii=False), ts, ts, site_id),
        )
    emit(
        {
            "ok": True,
            "site_id": site_id,
            "base_url": base_url,
            "run_id": run_id,
            "crawl_methods": sorted(crawl_methods),
            "anti_bot_signals": anti_bot_signals,
            "sitemaps_checked": len(seen_sitemaps),
            "sitemap_rows": sitemap_rows,
            "discovered_count": len(discovered),
            "queued_count": queued_count,
        }
    )


def crawl_process(args: argparse.Namespace) -> None:
    db_target = args.db
    with connect(db_target) as conn:
        site = ensure_crawl_site(conn, args.base_url) if args.base_url else conn.execute(
            "SELECT * FROM crawl_sites WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if not site:
            raise RuntimeError("No crawl site found. Run crawl-discover first or pass base_url.")
        site_id = site["id"]
        run_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO crawl_runs
              (id, site_id, kind, trigger, status, started_at, discovered_count, queued_count, fetched_count, failed_count)
            VALUES (?, ?, 'process', ?, 'running', ?, 0, 0, 0, 0)
            """,
            (run_id, site_id, args.trigger, now()),
        )
        rows = conn.execute(
            """
            SELECT * FROM crawl_urls
            WHERE site_id = ? AND status IN ('queued', 'failed') AND attempts < ?
            ORDER BY priority DESC, discovered_at ASC
            LIMIT ?
            """,
            (site_id, args.max_attempts, args.limit),
        ).fetchall()

    processed: list[dict[str, Any]] = []
    failed = 0
    for row in rows:
        url_id = row["id"]
        url = row["normalized_url"]
        try:
            with connect(db_target) as conn:
                conn.execute("UPDATE crawl_urls SET status = 'processing', attempts = attempts + 1 WHERE id = ?", (url_id,))
            status, headers, html = http_get_text(url, timeout=args.timeout)
            metadata, _links = parse_html(html, url)
            markdown = html_to_markdown(html)
            summary, summary_model = summarize_markdown(markdown, args.search_api, args.timeout, args.allow_offline_ai)
            vector, provider, vector_model = embed_text(summary or markdown[:1200], args.embedding_api, args.embedding_model, args.timeout, args.allow_offline_ai)
            page_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{site_id}:{url}"))
            vector_json = json.dumps(vector, separators=(",", ":"))
            html_hash = sha256_text(html)
            markdown_hash = sha256_text(markdown)
            quality_score = min(100, (30 if metadata.get("title") else 0) + (30 if len(markdown) > 500 else 10) + (20 if summary else 0) + (20 if status < 400 else 0))
            ts = now()
            with connect(db_target) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO crawl_pages
                      (id, site_id, url_id, url, canonical_url, title, meta_description, language, author,
                       published_at, modified_at, http_status, content_type, raw_html, html_hash, markdown,
                       markdown_hash, summary, summary_model, quality_score, status, fetched_at, processed_at, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'fetched', ?, ?, NULL)
                    """,
                    (
                        page_id,
                        site_id,
                        url_id,
                        url,
                        metadata.get("canonical_url"),
                        metadata.get("title"),
                        metadata.get("meta_description"),
                        metadata.get("language"),
                        metadata.get("author"),
                        metadata.get("published_at"),
                        metadata.get("modified_at"),
                        status,
                        headers.get("content-type"),
                        html,
                        html_hash,
                        markdown,
                        markdown_hash,
                        summary,
                        summary_model,
                        quality_score,
                        ts,
                        ts,
                    ),
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO crawl_page_embeddings
                      (id, page_id, source_field, provider, model, dimension, vector, vector_hash, created_at)
                    VALUES (?, ?, 'summary', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{page_id}:summary:{vector_model}")),
                        page_id,
                        provider,
                        vector_model,
                        len(vector),
                        pgvector_literal(vector) if conn.backend == "postgres" else vector_json,
                        sha256_text(vector_json),
                        ts,
                    ),
                )
                conn.execute("UPDATE crawl_urls SET status = 'fetched', last_error = NULL WHERE id = ?", (url_id,))
                conn.execute("UPDATE crawl_sites SET last_crawled_at = ?, updated_at = ? WHERE id = ?", (ts, ts, site_id))
            processed.append({"page_id": page_id, "url": url, "status": status, "markdown_chars": len(markdown), "summary_model": summary_model})
        except Exception as exc:
            failed += 1
            with connect(db_target) as conn:
                conn.execute(
                    "UPDATE crawl_urls SET status = 'failed', last_error = ? WHERE id = ?",
                    (str(exc)[:1000], url_id),
                )

    with connect(db_target) as conn:
        ts = now()
        conn.execute(
            """
            UPDATE crawl_runs
            SET status = ?, finished_at = ?, fetched_count = ?, failed_count = ?
            WHERE id = ?
            """,
            ("succeeded" if failed == 0 else "failed", ts, len(processed), failed, run_id),
        )
    emit({"ok": failed == 0, "site_id": site_id, "run_id": run_id, "processed_count": len(processed), "failed_count": failed, "pages": processed})


def crawl_run(args: argparse.Namespace) -> None:
    discover_args = argparse.Namespace(**vars(args))
    discover_args.limit = args.discover_limit
    discover_args.include_home_links = True
    discover_args.max_sitemaps = args.max_sitemaps
    crawl_discover(discover_args)
    process_args = argparse.Namespace(**vars(args))
    process_args.limit = args.process_limit
    process_args.max_attempts = args.max_attempts
    crawl_process(process_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Content factory MVP tasks")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Postgres database URL")
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

    crawl_discover_cmd = sub.add_parser("crawl-discover")
    crawl_discover_cmd.add_argument("base_url")
    crawl_discover_cmd.add_argument("--limit", type=int, default=200)
    crawl_discover_cmd.add_argument("--timeout", type=int, default=20)
    crawl_discover_cmd.add_argument("--trigger", default="manual")
    crawl_discover_cmd.add_argument("--include-home-links", action=argparse.BooleanOptionalAction, default=True)
    crawl_discover_cmd.add_argument("--max-sitemaps", type=int, default=20)
    crawl_discover_cmd.set_defaults(func=crawl_discover)

    crawl_process_cmd = sub.add_parser("crawl-process")
    crawl_process_cmd.add_argument("base_url", nargs="?")
    crawl_process_cmd.add_argument("--limit", type=int, default=20)
    crawl_process_cmd.add_argument("--timeout", type=int, default=30)
    crawl_process_cmd.add_argument("--trigger", default="manual")
    crawl_process_cmd.add_argument("--search-api", default=DEFAULT_SEARCH_API)
    crawl_process_cmd.add_argument("--embedding-api", default=DEFAULT_EMBEDDING_API)
    crawl_process_cmd.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    crawl_process_cmd.add_argument("--max-attempts", type=int, default=3)
    crawl_process_cmd.add_argument("--allow-offline-ai", action=argparse.BooleanOptionalAction, default=True)
    crawl_process_cmd.set_defaults(func=crawl_process)

    crawl_run_cmd = sub.add_parser("crawl-run")
    crawl_run_cmd.add_argument("base_url")
    crawl_run_cmd.add_argument("--discover-limit", type=int, default=200)
    crawl_run_cmd.add_argument("--process-limit", type=int, default=20)
    crawl_run_cmd.add_argument("--timeout", type=int, default=30)
    crawl_run_cmd.add_argument("--trigger", default="manual")
    crawl_run_cmd.add_argument("--search-api", default=DEFAULT_SEARCH_API)
    crawl_run_cmd.add_argument("--embedding-api", default=DEFAULT_EMBEDDING_API)
    crawl_run_cmd.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    crawl_run_cmd.add_argument("--max-sitemaps", type=int, default=20)
    crawl_run_cmd.add_argument("--max-attempts", type=int, default=3)
    crawl_run_cmd.add_argument("--allow-offline-ai", action=argparse.BooleanOptionalAction, default=True)
    crawl_run_cmd.set_defaults(func=crawl_run)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
