# search-scraper-mcp

MCP server and OpenAI-compatible HTTP API for web search and general web page scraping.

The project now uses Scrapling as the default scraping/search foundation and keeps CloakBrowser as an optional browser-backed scraping backend. It is no longer limited to Google AI Mode.

## Features

- MCP stdio tools:
  - `web_search`: search the web with the configured provider.
  - `ask`: ask a configured model website through a local browser session, or fall back to search when disabled.
  - `scrape_url`: fetch a URL and return readable page text.
- OpenAI-compatible HTTP API:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- Runtime console at `/`.
- Admin HTTP scrape endpoint at `POST /api/scrape`.
- Search providers:
  - `scrapling`: default no-key HTML search path.
  - `gemini_grounding`: Gemini API with Google Search grounding.
  - `brave`: Brave Search API.
  - `tavily`: Tavily Search API.
- Scraping backends:
  - `scrapling`: default HTTP fetcher.
  - `scrapling_chromium`: Scrapling dynamic Chromium fetcher.
  - `scrapling_stealthy`: Scrapling stealthy fetcher.
  - `cloakbrowser`: optional CloakBrowser backend.
- Website chat providers for `ask`:
  - `disabled`: default; `ask` falls back to configured search.
  - `deepseek`: asks `https://chat.deepseek.com/` through a browser.
  - `chatgpt`: asks `https://chatgpt.com/` through a browser.
  - `gemini`: asks `https://gemini.google.com/app` through a browser.

## Content Factory with n8n

See [docs/content-factory-n8n.md](docs/content-factory-n8n.md) for a practical design that uses n8n as the workflow orchestrator and this project as the search/scraping MCP capability.

For local n8n and n8n-mcp setup, see [docs/n8n-local-dev.md](docs/n8n-local-dev.md).

This content factory integration now includes three upstream GitHub projects:

| Upstream project | Role in this project | Install/deploy path |
| --- | --- | --- |
| [czlonkowski/n8n-mcp](https://github.com/czlonkowski/n8n-mcp) | n8n node knowledge, local MCP service, and offline workflow validation | Node dependency in `package.json` |
| [Zie619/n8n-workflows](https://github.com/Zie619/n8n-workflows) | Local searchable workflow template corpus for workflow design/reference | Synced into `vendor/n8n-workflows` with `npm.cmd run n8n:sync-templates` |
| [microsoft/markitdown](https://github.com/microsoft/markitdown) | Converts PDF/DOCX/PPTX/XLSX/HTML/Markdown source documents into Markdown research assets | Python optional dependency `.[content-factory]` and `.[all]` |

Initialize the SQLite MVP database:

```bash
python scripts/init_content_factory_db.py
```

On Windows PowerShell:

```powershell
.\scripts\init_content_factory_db.ps1
```

Import local n8n content factory workflows after n8n is running:

```powershell
.\scripts\import_content_factory_workflows.ps1
```

Validate local workflow JSON with n8n-mcp:

```powershell
npm.cmd run n8n:validate-workflows
```

Sync and index the public n8n workflow template corpus:

```powershell
npm.cmd run n8n:sync-templates
```

Ingest a document with MarkItDown:

```powershell
Copy-Item examples\content-factory\sample-source.md data\inbox\sample-source.md
scripts\run_content_factory_task.cmd seed-topic "document research" --id document-research-demo
scripts\run_content_factory_task.cmd ingest-document --topic-id document-research-demo --file data\inbox\sample-source.md
```

Use browser-backed scraping only on sites you own, are authorized to test, or are allowed to automate. Respect robots.txt, site terms, and applicable law.
Website chat automation is intended for personal research with your own logged-in sessions. The project does not bypass login, CAPTCHA, paywalls, or site restrictions.

## Install

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all]"
npm install
scrapling install
```

For CloakBrowser support, install and configure CloakBrowser according to its own documentation. The project keeps it as an optional backend via `.[cloakbrowser]` or `.[all]`.

For a lighter content-factory-only Python install without CloakBrowser:

```powershell
pip install -e ".[content-factory]"
npm install
npm.cmd run n8n:sync-templates
```

## Run MCP

```bash
gemini-search-mcp
```

Example Claude/Cursor MCP command:

```json
{
  "mcpServers": {
    "search-scraper": {
      "command": "gemini-search-mcp",
      "args": [],
      "env": {
        "GEMINI_SEARCH_PROVIDER": "scrapling",
        "GEMINI_SEARCH_SCRAPE_BACKEND": "scrapling"
      }
    }
  }
}
```

## Run HTTP API

```bash
gemini-search --host 127.0.0.1 --port 8080
```

Use a browser-backed scraping backend:

```bash
gemini-search --scrape-backend scrapling_chromium --headless
gemini-search --scrape-backend cloakbrowser --headless
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `GEMINI_SEARCH_PROVIDER` | `scrapling` | `scrapling`, `gemini_grounding`, `brave`, or `tavily`. |
| `GEMINI_SEARCH_SCRAPE_BACKEND` | `scrapling` | `scrapling`, `scrapling_chromium`, `scrapling_stealthy`, or `cloakbrowser`. |
| `HEADLESS` | `1` for MCP/Docker, `0` in desktop launcher | Browser-backed scraping headless mode. |
| `GEMINI_SEARCH_PROXY_SERVER` | empty | Optional proxy URL. |
| `GEMINI_API_KEY` | empty | Required for `gemini_grounding`. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model for grounded search. |
| `BRAVE_API_KEY` | empty | Required for `brave`. |
| `TAVILY_API_KEY` | empty | Required for `tavily`. |
| `TAVILY_SEARCH_DEPTH` | `basic` | Tavily depth, usually `basic` or `advanced`. |
| `WEB_CHAT_PROVIDER` | `disabled` | `disabled`, `deepseek`, `chatgpt`, or `gemini`. Controls the MCP `ask` path. |
| `WEB_CHAT_BACKEND` | `playwright` | `playwright` or `cloakbrowser` for website chat automation. |
| `WEB_CHAT_HEADLESS` | `0` locally | Use `0` for first login, `1` only after session is established. |
| `WEB_CHAT_PROFILE_DIR` | `profiles/web-chat/<provider>` | Persistent browser profile for website login sessions. |

## Website Chat Research Mode

First run in headed mode so you can log in manually:

```powershell
$env:WEB_CHAT_PROVIDER="deepseek"
$env:WEB_CHAT_BACKEND="playwright"
$env:WEB_CHAT_HEADLESS="0"
$env:WEB_CHAT_PROFILE_DIR="$PWD\profiles\web-chat\deepseek"
.\.venv-windows-build\Scripts\gemini-search.exe --host 127.0.0.1 --port 8080
```

Open the console at `http://127.0.0.1:8080/`, send a test prompt, and complete login in the browser window if the site asks for it. After the profile is logged in, MCP `ask` will use the website session. MCP `web_search` remains the general search tool and does not use the model website.

Equivalent MCP environment:

```json
{
  "WEB_CHAT_PROVIDER": "deepseek",
  "WEB_CHAT_BACKEND": "playwright",
  "WEB_CHAT_HEADLESS": "0",
  "WEB_CHAT_PROFILE_DIR": "profiles/web-chat/deepseek",
  "GEMINI_SEARCH_PROVIDER": "scrapling"
}
```

## Docker

```bash
docker compose up -d --build
```

The Docker image installs `.[all]` and runs `scrapling install` so Scrapling browser-backed fetchers can be used. Default runtime mode is the lighter `scrapling` backend.

## API Example

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-search\",\"messages\":[{\"role\":\"user\",\"content\":\"latest AI news today\"}]}"
```

Scrape a page:

```bash
curl http://localhost:8080/api/scrape \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example.com\",\"selector\":\"body\"}"
```
