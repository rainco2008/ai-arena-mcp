"""OpenAI-compatible API server using the Google AI Mode engine."""
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

from .engine import AIModeEngine


engine = AIModeEngine()
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
    return {
        "cdp_url": getattr(args, "cdp_url", None) if args else os.environ.get("CDP_URL"),
        "headless": not getattr(args, "no_headless", False) if args else _env_bool("HEADLESS", True),
        "channel": getattr(args, "channel", None) if args else os.environ.get("BROWSER_CHANNEL", "chromium"),
        "user_data_dir": (
            getattr(args, "user_data_dir", None) if args else None
        ) or os.environ.get("GEMINI_SEARCH_USER_DATA_DIR"),
        "browser_backend": (
            getattr(args, "browser_backend", None) if args else None
        ) or os.environ.get("GEMINI_SEARCH_BROWSER_BACKEND", "playwright"),
        "proxy_server": (
            getattr(args, "proxy_server", None) if args else None
        ) or os.environ.get("GEMINI_SEARCH_PROXY_SERVER"),
    }


async def _start_engine(config):
    global engine_started_at, last_error
    await engine.start(
        cdp_url=config.get("cdp_url"),
        headless=config["headless"],
        channel=config["channel"],
        user_data_dir=config.get("user_data_dir"),
        browser_backend=config.get("browser_backend"),
        proxy_server=config.get("proxy_server"),
    )
    engine_started_at = time.time()
    last_error = None


async def _restart_engine(config):
    global engine, runtime_config, engine_started_at, last_error
    async with engine_lock:
        await engine.stop()
        engine = AIModeEngine()
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime_config, last_error, engine_started_at
    runtime_config = dict(app.state.config)
    try:
        await _start_engine(runtime_config)
        print("AI Mode engine ready")
    except Exception as exc:
        last_error = str(exc)
        engine_started_at = None
        print(f"AI Mode engine failed to start: {exc}")
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
        "backend": runtime_config.get("browser_backend"),
    }


@app.get("/api/runtime")
async def get_runtime(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    safe_config = dict(runtime_config)
    safe_config["admin_token_required"] = bool(os.environ.get("ADMIN_TOKEN"))
    return safe_config


@app.put("/api/runtime")
async def update_runtime(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    body = await request.json()
    config = dict(runtime_config)
    allowed = {"cdp_url", "headless", "channel", "user_data_dir", "browser_backend", "proxy_server"}
    for key in allowed:
        if key in body:
            config[key] = body[key] or None
    if not config.get("channel"):
        config["channel"] = "chromium"
    if not config.get("browser_backend"):
        config["browser_backend"] = "playwright"
    await _restart_engine(config)
    return {"ok": True, "runtime": runtime_config}


@app.post("/api/runtime/restart")
async def restart_runtime(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    await _restart_engine(runtime_config)
    return {"ok": True, "runtime": runtime_config}


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
        text = await engine.ask(prompt, timeout_ms=timeout_ms)
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "elapsed_ms": int((time.time() - started) * 1000)},
            status_code=502,
        )
    return {
        "ok": True,
        "backend": runtime_config.get("browser_backend"),
        "elapsed_ms": int((time.time() - started) * 1000),
        "answer": text,
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
        text = await engine.ask(prompt)
    except Exception as e:
        return JSONResponse({"error": {"message": str(e), "type": "server_error"}}, status_code=502)
    return {"id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(text.split()), "total_tokens": len(prompt.split()) + len(text.split())}}


async def _stream(prompt, cid, created, model):
    yield _sse({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
    async for chunk in engine.ask_stream(prompt):
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
    parser = argparse.ArgumentParser(description="Gemini Search → OpenAI API")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--cdp-url", default=None, help="Connect to existing Chrome (e.g. http://127.0.0.1:9222)")
    parser.add_argument("--channel", default="chrome", choices=["chrome", "msedge", "chromium"])
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--user-data-dir", default=None, help="Persistent Chrome profile directory to create/reuse")
    parser.add_argument(
        "--browser-backend",
        choices=["request", "playwright", "cloakbrowser"],
        default=None,
        help="Backend. Defaults to GEMINI_SEARCH_BROWSER_BACKEND or playwright.",
    )
    parser.add_argument("--proxy-server", default=None, help="Chrome proxy server, e.g. socks5://127.0.0.1:7897")
    args = parser.parse_args()

    app.state.config = _initial_config(args)
    print(f"gemini-search-mcp v0.4.0")
    print(f"  API: http://{args.host}:{args.port}/v1")
    browser_backend = app.state.config["browser_backend"]
    browser_desc = args.cdp_url or f"{browser_backend}/{args.channel} (headless={not args.no_headless})"
    print(f"  Browser: {browser_desc}")
    if app.state.config.get("user_data_dir"):
        print(f"  User data dir: {app.state.config['user_data_dir']}")
    if app.state.config.get("proxy_server"):
        print(f"  Proxy: {app.state.config['proxy_server']}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
