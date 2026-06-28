# google-ai-mode

Reverse-proxy Google Search AI Mode as an OpenAI-compatible API.

**Pure protocol — no browser, no JS engine.** Just HTTP requests with cookies. Free, no API key, no Google account.

## How it works

Google Search AI Mode (powered by Gemini) serves AI answers via two HTTP endpoints:

1. `GET /search?q=<q>&udm=50` — returns a 360KB HTML page with session tokens (`data-srtst`, `data-xsrf-folwr-token`, `data-garc`, `data-stkp`, etc.) embedded in `data-*` attributes
2. `GET /async/folwr?<tokens>&q=<q>` — streams the AI answer as HTML chunks

This tool does both via plain `urllib` (zero browser dependencies), parses the answer HTML, and exposes it as an OpenAI-compatible API.

## Quick Start

```bash
pip install -e .

# Export cookies from a logged-in browser session (includes HttpOnly cookies)
# Then run:
python -m google_ai_mode --cookie-file cookies.txt
```

Server starts at `http://localhost:8080/v1`.

### Getting cookies

The `__Secure-STRP`, `NID`, `AEC`, `__Secure-BUCKET` cookies (some HttpOnly) are required for the full 360KB token-bearing response. Anonymous requests get only a 91KB JS-required shell.

**Export via browser DevTools:**
1. Open Google Search, log in (optional but improves reliability)
2. DevTools → Application → Cookies → `.google.com` / `.google.com.hk`
3. Copy all as `name=value; name=value` into `cookies.txt`

**Export via CDP** (if you have a Chrome debug port):
```bash
# See protocol.py get_cookies helper, or use a CDP cookie exporter
```

## Usage

```bash
# Non-streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google-ai-mode","messages":[{"role":"user","content":"What is the Bitcoin price today?"}]}'

# Streaming
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google-ai-mode","stream":true,"messages":[{"role":"user","content":"Explain quantum computing"}]}'
```

Works with any OpenAI-compatible client:

| Field | Value |
|-------|-------|
| Base URL | `http://localhost:8080/v1` |
| API Key | anything (unless `--api-key` set) |
| Model | `google-ai-mode` |

## CLI Options

```
--port          API port (default: 8080)
--host          Bind address (default: 0.0.0.0)
--cookie-file   File with Google cookies (includes HttpOnly)
--cookies       Inline cookie string
--api-key       Allowed API key (repeatable; omit to disable auth)
--proxy         HTTP proxy
```

## Features

- **Zero browser deps**: pure stdlib `urllib`, ~5MB footprint
- **OpenAI-compatible**: `/v1/chat/completions` (streaming + non-streaming), `/v1/models`
- **Real-time web search**: AI Mode grounds answers in live web results
- **Cookie auto-refresh**: captures `Set-Cookie` to keep tokens fresh
- **Retry with backoff**: handles HTTP 429 rate limits
- **System prompts**: concatenated with user message

## Architecture

```
User query
  → GET /search?q=<q>&udm=50  (with cookies)
  → extract tokens from data-* attributes
  → GET /async/folwr?<tokens>&q=<q>
  → parse answer from <div class="n6owBd"> containers
  → OpenAI-compatible response
```

Each request is stateless: a fresh page load + folwr per query. Token lifetime is ~5 minutes; cookies are refreshed automatically.

## Limitations

- **Cookies required**: needs browser-exported cookies (HttpOnly ones essential). Without them, Google returns a 91KB JS-required shell with no tokens.
- **Rate limits**: Google throttles aggressive use (~429 after bursts). Built-in retry handles this, but high-volume use needs cookie/IP rotation.
- **Streaming granularity**: folwr delivers answer in 2-5 chunks (~300ms intervals), not per-token.
- **Class-name fragility**: answer extraction relies on Google's CSS classes (`n6owBd`, `pTRUV`); Google may rename them.
- **No conversation memory**: each request is independent (fresh session).

## Rate Limits (important)

Google enforces **per-IP** limits on the search endpoint — AI Mode is stricter than regular search because of compute cost. Burst testing (~10+ requests/min) triggers HTTP 429 + CAPTCHA that can block an IP for hours.

### Mitigation (all built-in)

| Layer | Flag | What it does |
|-------|------|--------------|
| **Cookie rotation** | `--cookies-dir ./cookies/` | One file per Google account; rotates on each request, cools down on 429 |
| **Throttle** | `--min-interval 6` | Min seconds between requests + jitter |
| **Chrome fingerprint** | (automatic) | Uses `curl_cffi` to impersonate Chrome TLS/HTTP2 — triggers anti-bot far less than urllib |
| **Proxy / IP rotation** | `--proxy http://host:port` | The only way past a hard IP block. Rotate proxies for production volume |
| **429 backoff** | `--cooldown 180` | Failed cookies cool down with exponential backoff |

### Recommended deployment

```bash
# Production: multiple accounts + proxy pool
python -m google_ai_mode \
  --cookies-dir ./accounts/ \
  --proxy http://your-proxy-pool:8080 \
  --min-interval 8 \
  --api-key sk-yoursecret
```

Monitor pool health:
```bash
curl http://localhost:8080/v1/pool/stats
```

### If you get 429 now

You burst-tested and your IP is cooling off. Options:
1. Wait (can be hours for AI Mode endpoint)
2. Switch IP (proxy/VPN)
3. Use rotation pool from the start to avoid bursting one cookie/IP

## Docker

```bash
docker compose up -d
```

Mount cookies via volume or pass as env.

## License

MIT
