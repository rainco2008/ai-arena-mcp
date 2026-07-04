"""OpenAI-compatible API server using search and scraping providers."""
import asyncio
import json
import os
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


engine = SearchEngine()
engine_lock = asyncio.Lock()
runtime_config = {}
engine_started_at = None
last_error = None


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
    return JSONResponse({"message": "gemini-search API", "models": "/v1/models"})


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


@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": [{"id": "gemini-search", "object": "model", "created": 1719600000, "owned_by": "google"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    model = body.get("model", "gemini-search")

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
    print(f"gemini-search-mcp v0.4.0")
    print(f"  API: http://{args.host}:{args.port}/v1")
    print(f"  Search provider: {app.state.config['search_provider']}")
    print(f"  Web chat provider: {app.state.config['web_chat_provider']}")
    print(f"  Scrape backend: {app.state.config['scrape_backend']} (headless={app.state.config['headless']})")
    if app.state.config.get("proxy_server"):
        print(f"  Proxy: {app.state.config['proxy_server']}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
