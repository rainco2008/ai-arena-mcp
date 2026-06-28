"""OpenAI-compatible API server for Google AI Mode (pure protocol, no browser)."""
import json
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

from .protocol import AIModeClient, CookiePool


CONFIG = {
    "cookies": "",
    "cookie_file": None,
    "cookies_dir": None,
    "api_keys": [],
    "proxy": None,
    "min_interval": 6,
    "cooldown": 180,
    "_pool": None,
}


def _load_cookies_list() -> list:
    """Load cookies from inline, single file, or directory (multiple accounts)."""
    result = []
    if CONFIG["cookies"]:
        result.append(CONFIG["cookies"].strip())
    if CONFIG["cookie_file"]:
        try:
            with open(CONFIG["cookie_file"]) as fh:
                c = fh.read().strip()
                if c:
                    result.append(c)
        except Exception:
            pass
    if CONFIG["cookies_dir"]:
        try:
            for name in sorted(os.listdir(CONFIG["cookies_dir"])):
                path = os.path.join(CONFIG["cookies_dir"], name)
                if os.path.isfile(path):
                    with open(path) as fh:
                        c = fh.read().strip()
                        if c:
                            result.append(c)
        except Exception:
            pass
    return result


def _get_pool() -> CookiePool:
    if CONFIG["_pool"] is None:
        cookies_list = _load_cookies_list()
        CONFIG["_pool"] = CookiePool(
            cookies_list,
            min_interval=CONFIG["min_interval"],
            cooldown=CONFIG["cooldown"],
        )
    return CONFIG["_pool"]


def _make_client() -> AIModeClient:
    pool = _get_pool()
    # Single cookie → no pool (simpler, no throttle contention)
    if len(pool._entries) <= 1:
        cookies = _load_cookies_list()[0] if _load_cookies_list() else ""
        return AIModeClient(cookies=cookies, proxy=CONFIG.get("proxy"))
    return AIModeClient(cookie_pool=pool, proxy=CONFIG.get("proxy"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("google-ai-mode (pure protocol) ready")
    yield


app = FastAPI(lifespan=lifespan)


def _check_auth(request: Request) -> bool:
    keys = CONFIG.get("api_keys") or []
    if not keys:
        return True
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] in keys
    xk = request.headers.get("x-api-key", "")
    return xk in keys


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{
            "id": "google-ai-mode",
            "object": "model",
            "created": 1719600000,
            "owned_by": "google",
        }],
    }


@app.get("/v1/pool/stats")
async def pool_stats():
    """Health stats for the cookie rotation pool."""
    if CONFIG["_pool"] is None:
        return {"enabled": False, "reason": "single-cookie mode (no pool)"}
    return {"enabled": True, "entries": CONFIG["_pool"].stats()}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if not _check_auth(request):
        return JSONResponse({"error": {"message": "invalid api key", "type": "invalid_request_error"}}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    model = body.get("model", "google-ai-mode")

    prompt = _build_prompt(messages)
    if not prompt:
        return JSONResponse({"error": {"message": "No user message", "type": "invalid_request_error"}}, status_code=400)

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if stream:
        return StreamingResponse(
            _stream_response(prompt, completion_id, created, model),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    import asyncio
    loop = asyncio.get_event_loop()
    client = _make_client()
    try:
        text = await loop.run_in_executor(None, client.ask, prompt)
    except Exception as e:
        return JSONResponse({"error": {"message": str(e), "type": "api_error"}}, status_code=502)

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(text.split()),
            "total_tokens": len(prompt.split()) + len(text.split()),
        },
    }


async def _stream_response(prompt: str, completion_id: str, created: int, model: str):
    import asyncio
    yield _sse({"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})

    client = _make_client()
    loop = asyncio.get_event_loop()

    def _collect():
        chunks = []
        try:
            for chunk in client.ask_stream(prompt):
                chunks.append(chunk)
        except Exception as e:
            chunks.append(f"[error: {e}]")
        return chunks

    chunks = await loop.run_in_executor(None, _collect)
    for chunk in chunks:
        yield _sse({
            "id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
            "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
        })

    yield _sse({
        "id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    })
    yield "data: [DONE]\n\n"


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_prompt(messages: list) -> str:
    system = ""
    user = ""
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
        if role == "system":
            system = content
        elif role == "user":
            user = content
    if system and user:
        return f"{system}\n\n{user}"
    return user


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Google AI Mode → OpenAI API (pure protocol, no browser)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single cookie file
  python -m google_ai_mode --cookie-file cookies.txt

  # Multiple cookie files (rotation pool, mitigates rate limits)
  python -m google_ai_mode --cookies-dir ./cookies/

  # With HTTP proxy for IP rotation
  python -m google_ai_mode --cookies-dir ./cookies/ --proxy http://proxy:8080

  # Inline cookies + API key auth
  python -m google_ai_mode --cookies "NID=...; AEC=..." --api-key sk-mykey
""",
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--cookie-file", type=str, default=None, help="Single cookies file")
    parser.add_argument("--cookies-dir", type=str, default=None, help="Directory of cookie files (one per Google account) for rotation")
    parser.add_argument("--cookies", type=str, default=None, help="Inline cookie string")
    parser.add_argument("--api-key", type=str, default=None, action="append", help="Allowed API key (repeatable)")
    parser.add_argument("--proxy", type=str, default=None, help="HTTP/HTTPS proxy URL")
    parser.add_argument("--min-interval", type=float, default=6.0, help="Min seconds between requests (throttle)")
    parser.add_argument("--cooldown", type=float, default=180.0, help="Seconds to cool a cookie after HTTP 429")
    args = parser.parse_args()

    if args.cookie_file:
        CONFIG["cookie_file"] = args.cookie_file
    if args.cookies_dir:
        CONFIG["cookies_dir"] = args.cookies_dir
    if args.cookies:
        CONFIG["cookies"] = args.cookies
    if args.api_key:
        CONFIG["api_keys"] = args.api_key
    if args.proxy:
        CONFIG["proxy"] = args.proxy
    CONFIG["min_interval"] = args.min_interval
    CONFIG["cooldown"] = args.cooldown

    n_cookies = len(_load_cookies_list())
    print(f"google-ai-mode v0.2.0 (pure protocol)")
    print(f"  Listening:    http://{args.host}:{args.port}/v1")
    print(f"  Cookies:      {n_cookies} set(s) " + ("(rotation pool)" if n_cookies > 1 else ""))
    print(f"  Throttle:     min {args.min_interval}s between requests")
    print(f"  429 cooldown: {args.cooldown}s")
    print(f"  Proxy:        {args.proxy or 'none'}")
    print(f"  Auth:         {'enabled (' + str(len(args.api_key)) + ' keys)' if args.api_key else 'disabled'}")
    print()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
