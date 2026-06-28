"""OpenAI-compatible API server for Google AI Mode."""
import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

from .engine import SessionPool


pool = SessionPool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = app.state.config
    print(f"Initializing {cfg['pool_size']} session(s)...")
    await pool.start(
        cdp_url=cfg.get("cdp_url"),
        headless=cfg["headless"],
        channel=cfg["channel"],
    )
    pool.size = cfg["pool_size"]
    print(f"Ready. Pool: {len(pool.sessions)} session(s)")
    yield
    await pool.stop()


app = FastAPI(lifespan=lifespan)


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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    # Build prompt from messages (use last user message)
    prompt = _build_prompt(messages)
    if not prompt:
        return JSONResponse(
            {"error": {"message": "No user message found", "type": "invalid_request_error"}},
            status_code=400,
        )

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model = body.get("model", "google-ai-mode")

    if stream:
        return StreamingResponse(
            _stream_response(prompt, completion_id, created, model),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    session = await pool.acquire()
    try:
        text = await session.ask(prompt)
    finally:
        pool.release(session)

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
    # Initial role chunk
    yield _sse({"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})

    session = await pool.acquire()
    try:
        async for chunk in session.ask_stream(prompt):
            yield _sse({
                "id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
            })
    finally:
        pool.release(session)

    yield _sse({
        "id": completion_id, "object": "chat.completion.chunk", "created": created, "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    })
    yield "data: [DONE]\n\n"


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_prompt(messages: list) -> str:
    """Extract prompt from messages. Concatenates system + last user message."""
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
        description="Google AI Mode → OpenAI-compatible API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Self-launch Chrome (recommended for first try)
  python -m google_ai_mode --channel chrome

  # Connect to existing Chrome with remote debugging
  python -m google_ai_mode --cdp-url http://127.0.0.1:9222

  # Multiple concurrent sessions
  python -m google_ai_mode --pool-size 3
""",
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--cdp-url", type=str, default=None,
                        help="Connect to existing Chrome via CDP (e.g. http://127.0.0.1:9222)")
    parser.add_argument("--channel", type=str, default="chrome",
                        choices=["chrome", "msedge", "chromium"],
                        help="Browser channel: chrome (system), msedge, or chromium (bundled)")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_true", help="Show browser window (debug)")
    parser.add_argument("--pool-size", type=int, default=1,
                        help="Number of concurrent browser tabs")
    args = parser.parse_args()

    headless = not args.no_headless

    app.state.config = {
        "cdp_url": args.cdp_url,
        "channel": args.channel,
        "headless": headless,
        "pool_size": args.pool_size,
    }

    print(f"google-ai-mode v0.1.0")
    print(f"  Listening:  http://{args.host}:{args.port}/v1")
    print(f"  Browser:    {args.cdp_url or f'{args.channel} (self-launch, headless={headless})'}")
    print(f"  Pool size:  {args.pool_size}")
    print()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
