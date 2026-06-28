# google-ai-mode

Reverse-proxy Google Search AI Mode as an OpenAI-compatible API.

Free, no API key, no Google account. Responses include real-time web search results.

## How it works

Google Search AI Mode (powered by Gemini) provides grounded AI answers with live web search. This tool automates a real Chrome browser to interact with AI Mode and exposes responses through a standard OpenAI-compatible API.

## Quick Start

```bash
# Install
pip install playwright fastapi uvicorn
playwright install chrome

# Run
python -m google_ai_mode
```

Server starts at `http://localhost:8080/v1`. That's it.

## Usage

```bash
# Non-streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google-ai-mode","messages":[{"role":"user","content":"What happened in the news today?"}]}'

# Streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google-ai-mode","stream":true,"messages":[{"role":"user","content":"Explain quantum computing"}]}'
```

Works with any OpenAI-compatible client (Cherry Studio, ChatBox, Open WebUI, etc.):

| Field | Value |
|-------|-------|
| Base URL | `http://localhost:8080/v1` |
| API Key | anything |
| Model | `google-ai-mode` |

## Platform Support

| Platform | Browser | Status |
|----------|---------|--------|
| Windows | Chrome / Edge | Works out of the box |
| macOS | Chrome / Edge | Works out of the box |
| Linux | Chrome / Chromium | Works (may need `playwright install chrome`) |
| Docker | Bundled Chromium | Works with stealth patches |

The server auto-detects your system browser. Priority: Chrome → Edge → Chromium.

## Options

```
python -m google_ai_mode [OPTIONS]

--port          API port (default: 8080)
--host          Bind address (default: 0.0.0.0)
--cdp-url       Connect to existing Chrome DevTools (e.g. http://127.0.0.1:9222)
--channel       Browser: chrome, msedge, chromium (default: chrome)
--no-headless   Show browser window for debugging
--pool-size N   Concurrent browser tabs (default: 1)
```

### If you get CAPTCHA errors

Google may detect automated browsers. Solutions in order of reliability:

1. **Use system Chrome** (default): `python -m google_ai_mode --channel chrome`
2. **Connect to your own Chrome**: Launch Chrome with `--remote-debugging-port=9222`, then `python -m google_ai_mode --cdp-url http://127.0.0.1:9222`
3. **Try Edge**: `python -m google_ai_mode --channel msedge`

## Docker

```bash
docker compose up -d
```

Note: Docker uses bundled Chromium which may trigger CAPTCHA more often. For production, prefer connecting to an external Chrome via `--cdp-url`.

## Features

- OpenAI-compatible `/v1/chat/completions` and `/v1/models`
- SSE streaming
- Real-time web search grounding (built into AI Mode)
- System prompt support
- Concurrent request pool (multi-tab)
- Auto-recovery on session failure
- Cross-platform (Windows / macOS / Linux / Docker)

## Limitations

- First response takes ~5-10s (Gemini searches the web before answering)
- Streaming is chunked (~300ms intervals, not per-token)
- No conversation memory between requests (each is independent)
- No native function/tool calling (AI Mode handles search internally)
- Requires a Chrome-family browser installed

## License

MIT
