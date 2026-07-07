"""OpenAI-compatible API server using search and scraping providers."""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from .providers import SearchEngine, mask_secret, merge_secret, normalize_scrape_backend, normalize_search_provider
from .web_chat import normalize_web_chat_provider
from content_factory.cli import DEFAULT_DB as CONTENT_FACTORY_DB
from content_factory.db import connect as connect_content_db, is_postgres_target


engine = SearchEngine()
engine_lock = asyncio.Lock()
runtime_config = {}
engine_started_at = None
last_error = None


def _content_db_target() -> str:
    return (
        os.environ.get("CONTENTPILOT_DATABASE_URL")
        or os.environ.get("CONTENT_FACTORY_DB")
        or os.environ.get("CONTENT_FACTORY_DATABASE_URL")
        or str(CONTENT_FACTORY_DB)
    )


def _content_db():
    return connect_content_db(_content_db_target())


def _rows(conn, query: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _scalar(conn, query: str, params: tuple = ()):
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _table_exists(conn, name: str) -> bool:
    if conn.backend == "postgres":
        return bool(
            conn.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = ?",
                (name,),
            ).fetchone()
        )
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone())


def _empty_content_factory_state() -> dict:
    return {
        "db": str(_content_db_target()),
        "ready": False,
        "summary": {},
        "recent_runs": [],
        "sites": [],
        "urls": [],
        "pages": [],
        "topics": [],
        "assets": [],
        "content_items": [],
        "reviews": [],
        "publications": [],
        "metrics": [],
        "workflows": [],
    }


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _insert_task_log(task_id: str, stream: str, message: str) -> None:
    try:
        with _content_db() as conn:
            conn.execute(
                """
                INSERT INTO resource_task_logs (id, task_id, stream, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), task_id, stream, message[-12000:], _utc_now()),
            )
    except Exception:
        pass


def _run_resource_task(task_id: str, args: list[str]) -> None:
    started = time.time()
    started_at = _utc_now()
    try:
        with _content_db() as conn:
            conn.execute(
                "UPDATE resource_tasks SET status = ?, progress = ?, started_at = ?, updated_at = ? WHERE id = ?",
                ("running", 5, started_at, started_at, task_id),
            )
        completed = subprocess.run(args, cwd=Path.cwd(), capture_output=True, text=True, timeout=1800)
        finished_at = _utc_now()
        status = "succeeded" if completed.returncode == 0 else "failed"
        if completed.stdout:
            _insert_task_log(task_id, "stdout", completed.stdout)
        if completed.stderr:
            _insert_task_log(task_id, "stderr", completed.stderr)
        with _content_db() as conn:
            conn.execute(
                """
                UPDATE resource_tasks
                SET status = ?, progress = ?, finished_at = ?, elapsed_ms = ?, returncode = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    100,
                    finished_at,
                    int((time.time() - started) * 1000),
                    completed.returncode,
                    completed.stderr[-4000:] if completed.returncode != 0 else None,
                    finished_at,
                    task_id,
                ),
            )
    except Exception as exc:
        finished_at = _utc_now()
        _insert_task_log(task_id, "error", str(exc))
        try:
            with _content_db() as conn:
                conn.execute(
                    """
                    UPDATE resource_tasks
                    SET status = ?, progress = ?, finished_at = ?, elapsed_ms = ?, error = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    ("failed", 100, finished_at, int((time.time() - started) * 1000), str(exc), finished_at, task_id),
                )
        except Exception:
            pass


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value not in ("0", "false", "False", "no", "NO")


def _initial_config(args=None):
    if args:
        headless = bool(getattr(args, "headless", False))
        if getattr(args, "no_headless", False):
            headless = False
    else:
        headless = _env_bool("HEADLESS", False)

    return {
        "headless": headless,
        "scrape_backend": (
            getattr(args, "scrape_backend", None) if args else None
        ) or os.environ.get("GEMINI_SEARCH_SCRAPE_BACKEND", "scrapling"),
        "proxy_server": (
            getattr(args, "proxy_server", None) if args else None
        ) or os.environ.get("GEMINI_SEARCH_PROXY_SERVER"),
        "search_provider": (
            getattr(args, "search_provider", None) if args else None
        ) or os.environ.get("GEMINI_SEARCH_PROVIDER", "scrapling"),
        "web_chat_provider": (
            getattr(args, "web_chat_provider", None) if args else None
        ) or os.environ.get("WEB_CHAT_PROVIDER", "disabled"),
        "web_chat_backend": (
            getattr(args, "web_chat_backend", None) if args else None
        ) or os.environ.get("WEB_CHAT_BACKEND", "playwright"),
        "web_chat_headless": _env_bool("WEB_CHAT_HEADLESS", False),
        "web_chat_profile_dir": os.environ.get("WEB_CHAT_PROFILE_DIR"),
        "gemini_api_key": os.environ.get("GEMINI_API_KEY"),
        "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "brave_api_key": os.environ.get("BRAVE_API_KEY"),
        "tavily_api_key": os.environ.get("TAVILY_API_KEY"),
        "tavily_search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "basic"),
    }


async def _start_engine(config):
    global engine_started_at, last_error
    await engine.start(**config)
    engine_started_at = time.time()
    last_error = None


async def _restart_engine(config):
    global engine, runtime_config, engine_started_at, last_error
    async with engine_lock:
        await engine.stop()
        engine = SearchEngine()
        runtime_config = dict(config)
        try:
            await _start_engine(runtime_config)
        except Exception as exc:
            last_error = str(exc)
            engine_started_at = None
            raise


def _admin_allowed(request: Request) -> bool:
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        return True
    auth = request.headers.get("authorization", "")
    return auth == f"Bearer {token}"


def _require_admin(request: Request):
    if not _admin_allowed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


def _safe_runtime_config(config: dict) -> dict:
    safe_config = dict(config)
    safe_config["gemini_api_key"] = mask_secret(safe_config.get("gemini_api_key"))
    safe_config["brave_api_key"] = mask_secret(safe_config.get("brave_api_key"))
    safe_config["tavily_api_key"] = mask_secret(safe_config.get("tavily_api_key"))
    return safe_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime_config, last_error, engine_started_at
    runtime_config = dict(app.state.config)
    if _env_bool("GEMINI_SEARCH_SKIP_ENGINE_START", False):
        last_error = "Search/scraping engine start skipped by GEMINI_SEARCH_SKIP_ENGINE_START=1"
        engine_started_at = None
        print(last_error)
    else:
        try:
            await _start_engine(runtime_config)
            print("Search and scraping engine ready")
        except Exception as exc:
            last_error = str(exc)
            engine_started_at = None
            safe_error = str(exc).encode("ascii", "backslashreplace").decode("ascii")
            print(f"Search and scraping engine failed to start: {safe_error}")
    yield
    await engine.stop()


app = FastAPI(lifespan=lifespan)
app.state.config = _initial_config()
static_dir = Path(__file__).with_name("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def console_index():
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"message": "ContentPilot API", "models": "/v1/models"})


@app.get("/api/health")
async def health(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    return {
        "ok": engine_started_at is not None,
        "started_at": engine_started_at,
        "uptime_seconds": int(time.time() - engine_started_at) if engine_started_at else None,
        "last_error": last_error,
        "backend": runtime_config.get("scrape_backend"),
        "search_provider": runtime_config.get("search_provider"),
        "web_chat_provider": runtime_config.get("web_chat_provider"),
    }


@app.get("/api/runtime")
async def get_runtime(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    safe_config = _safe_runtime_config(runtime_config)
    safe_config["admin_token_required"] = bool(os.environ.get("ADMIN_TOKEN"))
    return safe_config


@app.put("/api/runtime")
async def update_runtime(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    body = await request.json()
    config = dict(runtime_config)
    allowed = {
        "headless",
        "scrape_backend",
        "proxy_server",
        "search_provider",
        "web_chat_provider",
        "web_chat_backend",
        "web_chat_headless",
        "web_chat_profile_dir",
        "gemini_model",
        "tavily_search_depth",
    }
    for key in allowed:
        if key in body:
            config[key] = body[key] or None
    for key in ("gemini_api_key", "brave_api_key", "tavily_api_key"):
        if key in body:
            config[key] = merge_secret(config.get(key), body.get(key))
    config["scrape_backend"] = normalize_scrape_backend(config.get("scrape_backend"))
    config["search_provider"] = normalize_search_provider(config.get("search_provider"))
    config["web_chat_provider"] = normalize_web_chat_provider(config.get("web_chat_provider"))
    if not config.get("gemini_model"):
        config["gemini_model"] = "gemini-2.5-flash"
    if not config.get("tavily_search_depth"):
        config["tavily_search_depth"] = "basic"
    await _restart_engine(config)
    return {"ok": True, "runtime": _safe_runtime_config(runtime_config)}


@app.post("/api/runtime/restart")
async def restart_runtime(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    await _restart_engine(runtime_config)
    return {"ok": True, "runtime": _safe_runtime_config(runtime_config)}


@app.post("/api/test")
async def test_prompt(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    timeout_ms = int(body.get("timeout_ms", 45000))
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)
    if engine_started_at is None:
        return JSONResponse(
            {"ok": False, "error": last_error or "Engine is not ready", "elapsed_ms": 0},
            status_code=503,
        )

    started = time.time()
    try:
        text = await engine.chat(prompt, timeout_ms=timeout_ms)
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "elapsed_ms": int((time.time() - started) * 1000)},
            status_code=502,
        )
    return {
        "ok": True,
        "backend": runtime_config.get("scrape_backend"),
        "search_provider": runtime_config.get("search_provider"),
        "web_chat_provider": runtime_config.get("web_chat_provider"),
        "elapsed_ms": int((time.time() - started) * 1000),
        "answer": text,
    }


@app.post("/api/scrape")
async def scrape_url(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    body = await request.json()
    url = body.get("url", "").strip()
    selector = body.get("selector") or None
    timeout_ms = int(body.get("timeout_ms", 45000))
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)
    if engine_started_at is None:
        return JSONResponse(
            {"ok": False, "error": last_error or "Engine is not ready", "elapsed_ms": 0},
            status_code=503,
        )

    started = time.time()
    try:
        text = await engine.scrape(url, selector=selector, timeout_ms=timeout_ms)
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "elapsed_ms": int((time.time() - started) * 1000)},
            status_code=502,
        )
    return {
        "ok": True,
        "backend": runtime_config.get("scrape_backend"),
        "elapsed_ms": int((time.time() - started) * 1000),
        "content": text,
    }


@app.get("/api/content-factory/overview")
async def content_factory_overview(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied

    db_path = _content_db_target()
    if not is_postgres_target(db_path) and not Path(db_path).exists():
        return _empty_content_factory_state()

    with _content_db() as conn:
        if not _table_exists(conn, "topic_pool"):
            return _empty_content_factory_state()

        has_crawl = _table_exists(conn, "crawl_sites")
        summary = {
            "topics": _scalar(conn, "SELECT COUNT(*) FROM topic_pool"),
            "research_assets": _scalar(conn, "SELECT COUNT(*) FROM research_assets"),
            "content_items": _scalar(conn, "SELECT COUNT(*) FROM content_items"),
            "reviews": _scalar(conn, "SELECT COUNT(*) FROM review_records"),
            "publications": _scalar(conn, "SELECT COUNT(*) FROM publication_records"),
            "crawl_sites": _scalar(conn, "SELECT COUNT(*) FROM crawl_sites") if has_crawl else 0,
            "queued_urls": _scalar(conn, "SELECT COUNT(*) FROM crawl_urls WHERE status = 'queued'") if has_crawl else 0,
            "crawl_pages": _scalar(conn, "SELECT COUNT(*) FROM crawl_pages") if has_crawl else 0,
            "embeddings": _scalar(conn, "SELECT COUNT(*) FROM crawl_page_embeddings") if has_crawl else 0,
        }
        state = {
            "db": str(db_path),
            "ready": True,
            "summary": summary,
            "recent_runs": _rows(
                conn,
                """
                SELECT r.*, s.domain, s.base_url
                FROM crawl_runs r
                JOIN crawl_sites s ON s.id = r.site_id
                ORDER BY r.started_at DESC
                LIMIT 20
                """,
            )
            if has_crawl
            else [],
            "sites": _rows(
                conn,
                """
                SELECT id, base_url, domain, status, last_discovered_at, last_crawled_at, created_at
                FROM crawl_sites
                ORDER BY updated_at DESC
                LIMIT 50
                """,
            )
            if has_crawl
            else [],
            "urls": _rows(
                conn,
                """
                SELECT u.url, u.source, u.priority, u.status, u.attempts, u.discovered_at, s.domain
                FROM crawl_urls u
                JOIN crawl_sites s ON s.id = u.site_id
                ORDER BY u.discovered_at DESC
                LIMIT 100
                """,
            )
            if has_crawl
            else [],
            "pages": _rows(
                conn,
                """
                SELECT p.url, p.title, p.http_status, p.quality_score, p.summary_model, p.fetched_at, s.domain
                FROM crawl_pages p
                JOIN crawl_sites s ON s.id = p.site_id
                ORDER BY p.fetched_at DESC
                LIMIT 100
                """,
            )
            if has_crawl
            else [],
            "topics": _rows(
                conn,
                """
                SELECT id, keyword, source, intent, priority, status, owner, due_at, created_at, updated_at
                FROM topic_pool
                ORDER BY priority DESC, created_at DESC
                LIMIT 100
                """,
            ),
            "assets": _rows(
                conn,
                """
                SELECT a.id, a.topic_id, t.keyword, a.url, a.title, a.reliability, a.collected_at
                FROM research_assets a
                LEFT JOIN topic_pool t ON t.id = a.topic_id
                ORDER BY a.collected_at DESC
                LIMIT 100
                """,
            ),
            "content_items": _rows(
                conn,
                """
                SELECT c.id, c.topic_id, t.keyword, c.channel, c.seo_title, c.status, c.created_at, c.updated_at
                FROM content_items c
                LEFT JOIN topic_pool t ON t.id = c.topic_id
                ORDER BY c.updated_at DESC
                LIMIT 100
                """,
            ),
            "reviews": _rows(
                conn,
                """
                SELECT r.id, r.content_id, c.seo_title, r.reviewer, r.decision, r.created_at
                FROM review_records r
                LEFT JOIN content_items c ON c.id = r.content_id
                ORDER BY r.created_at DESC
                LIMIT 100
                """,
            ),
            "publications": _rows(
                conn,
                """
                SELECT p.id, p.content_id, c.seo_title, p.channel, p.status, p.url, p.published_at, p.created_at
                FROM publication_records p
                LEFT JOIN content_items c ON c.id = p.content_id
                ORDER BY p.created_at DESC
                LIMIT 100
                """,
            ),
            "metrics": _rows(
                conn,
                """
                SELECT m.id, m.content_id, c.seo_title, m.channel, m.impressions, m.clicks, m.conversions, m.engagement, m.collected_at
                FROM performance_metrics m
                LEFT JOIN content_items c ON c.id = m.content_id
                ORDER BY m.collected_at DESC
                LIMIT 100
                """,
            ),
            "workflows": [
                {"name": json.loads(path.read_text(encoding="utf-8")).get("name", path.stem), "file": path.name}
                for path in sorted((Path.cwd() / "workflows" / "n8n").glob("*.json"))
            ],
        }
    return state


@app.post("/api/content-factory/task")
async def content_factory_task(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied

    body = await request.json()
    task = str(body.get("task", "")).strip()
    allowed = {
        "init-db",
        "discover",
        "research",
        "draft",
        "quality-gate",
        "approval-router",
        "publish",
        "metrics-feedback",
        "crawl-discover",
        "crawl-process",
        "crawl-run",
    }
    if task not in allowed:
        return JSONResponse({"error": "unsupported task"}, status_code=400)

    args = [sys.executable, str(Path.cwd() / "content_factory_cli.py"), "--db", str(_content_db_target()), task]
    if task in {"crawl-discover", "crawl-process", "crawl-run"}:
        base_url = str(body.get("base_url", "")).strip()
        if not base_url:
            return JSONResponse({"error": "base_url is required"}, status_code=400)
        args.append(base_url)
    if task == "discover":
        seeds = str(body.get("seeds", "")).strip()
        if seeds:
            args.extend(["--seeds", seeds])
    for key, cli_key in (
        ("limit", "--limit"),
        ("discover_limit", "--discover-limit"),
        ("process_limit", "--process-limit"),
    ):
        value = body.get(key)
        if value not in (None, ""):
            args.extend([cli_key, str(value)])

    task_id = str(uuid.uuid4())
    ts = _utc_now()
    with _content_db() as conn:
        conn.execute(
            """
            INSERT INTO resource_tasks
              (id, task_type, status, trigger, params, progress, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                task,
                "queued",
                "api",
                json.dumps(body, ensure_ascii=False),
                0,
                ts,
                ts,
            ),
        )

    worker = threading.Thread(target=_run_resource_task, args=(task_id, args), daemon=True)
    worker.start()
    return JSONResponse({"ok": True, "task_id": task_id, "task": task, "status": "queued"}, status_code=202)


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "contentpilot", "object": "model", "created": 1719600000, "owned_by": "contentpilot"},
            {"id": "gemini-search", "object": "model", "created": 1719600000, "owned_by": "contentpilot"},
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    model = body.get("model", "contentpilot")

    prompt = _build_prompt(messages)
    if not prompt:
        return JSONResponse({"error": {"message": "No user message", "type": "invalid_request_error"}}, status_code=400)
    if engine_started_at is None:
        return JSONResponse(
            {"error": {"message": last_error or "Engine is not ready", "type": "server_error"}},
            status_code=503,
        )

    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if stream:
        return StreamingResponse(_stream(prompt, cid, created, model), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

    try:
        text = await engine.chat(prompt)
    except Exception as e:
        return JSONResponse({"error": {"message": str(e), "type": "server_error"}}, status_code=502)
    return {"id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(text.split()), "total_tokens": len(prompt.split()) + len(text.split())}}


async def _stream(prompt, cid, created, model):
    yield _sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
    async for chunk in engine.chat_stream(prompt):
        yield _sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                    "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}]})
    yield _sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    yield "data: [DONE]\n\n"


def _sse(d): return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _build_prompt(messages):
    system = user = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
        if role == "system": system = content
        elif role == "user": user = content
    return f"{system}\n\n{user}".strip() if system else user


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Search and scraping -> OpenAI API")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--headless", action="store_true", help="Run browser-backed scraping in headless mode")
    parser.add_argument("--no-headless", action="store_true", help="Run browser-backed scraping with a visible window")
    parser.add_argument(
        "--scrape-backend",
        choices=["scrapling", "scrapling_chromium", "scrapling_stealthy", "cloakbrowser"],
        default=None,
        help="Scraping backend. Defaults to GEMINI_SEARCH_SCRAPE_BACKEND or scrapling.",
    )
    parser.add_argument("--proxy-server", default=None, help="Proxy server, e.g. socks5://127.0.0.1:7897")
    parser.add_argument(
        "--search-provider",
        choices=["scrapling", "gemini_grounding", "brave", "tavily"],
        default=None,
        help="Search provider. Defaults to GEMINI_SEARCH_PROVIDER or scrapling.",
    )
    parser.add_argument(
        "--web-chat-provider",
        choices=["disabled", "deepseek", "chatgpt", "gemini"],
        default=None,
        help="Website chat provider for ask/chat completions. Defaults to WEB_CHAT_PROVIDER or disabled.",
    )
    parser.add_argument(
        "--web-chat-backend",
        choices=["playwright", "cloakbrowser"],
        default=None,
        help="Browser backend for website chat automation.",
    )
    args = parser.parse_args()

    app.state.config = _initial_config(args)
    print("ContentPilot v0.4.0")
    print(f"  API: http://{args.host}:{args.port}/v1")
    print(f"  Search provider: {app.state.config['search_provider']}")
    print(f"  Web chat provider: {app.state.config['web_chat_provider']}")
    print(f"  Scrape backend: {app.state.config['scrape_backend']} (headless={app.state.config['headless']})")
    if app.state.config.get("proxy_server"):
        print(f"  Proxy: {app.state.config['proxy_server']}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
