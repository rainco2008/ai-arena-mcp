# n8n Local Development

This project runs n8n and n8n-mcp through Docker Compose.

## Services

| Service | URL | Purpose |
| --- | --- | --- |
| `gemini-search` | `http://localhost:8080` | Search, scraping, and OpenAI-compatible API |
| `n8n` | `http://localhost:5678` | Workflow builder and scheduler |
| `n8n-mcp` | `http://localhost:3000/mcp` | MCP HTTP endpoint for n8n workflow design tools |

## Start

```powershell
docker compose pull n8n n8n-mcp
docker compose up -d --build
```

Open n8n:

```text
http://localhost:5678
```

The local n8n-mcp auth token defaults to:

```text
local-dev-n8n-mcp-token-change-me-123456
```

For real use, set your own token before starting:

```powershell
$env:N8N_MCP_AUTH_TOKEN = "replace-with-a-random-32-plus-character-token"
docker compose up -d
```

## Connect n8n to n8n-mcp

In an n8n workflow, add the MCP Client Tool node and use:

```text
Server URL: http://n8n-mcp:3000/mcp
Auth Token: value of N8N_MCP_AUTH_TOKEN
Transport: HTTP Streamable / SSE
```

Use `http://n8n-mcp:3000/mcp` from inside n8n because both containers are on the same Docker Compose network.

## Connect n8n to this project's API

From inside n8n, call the search/scraping service by Docker service name:

```text
http://gemini-search:8080/api/scrape
http://gemini-search:8080/v1/chat/completions
```

The content factory SQLite file is mounted into n8n at:

```text
/data/content_factory.sqlite
```

## API key for n8n-mcp management tools

n8n-mcp documentation and validation tools work without an n8n API key. Workflow management tools require an API key.

After first login to n8n:

1. Open n8n Settings.
2. Create an API key.
3. Restart compose with `N8N_API_KEY` set.

PowerShell example:

```powershell
$env:N8N_API_KEY = "n8n_api_xxx"
docker compose up -d
```

## Production notes

The production compose exposes n8n through Caddy at `N8N_DOMAIN`.

n8n-mcp is intentionally not public by default. Keep it internal unless you add separate authentication, TLS, and network restrictions.

## npm fallback

If Docker is not installed, use the npm scripts:

```powershell
npm install
npm run n8n
```

In another terminal:

```powershell
npm run n8n:mcp:http
```

Local URLs:

```text
n8n: http://localhost:5678
n8n-mcp: http://localhost:3000/mcp
```

## Local content factory workflows

Install Node dependencies:

```powershell
npm install
```

Sync the public workflow template corpus from `Zie619/n8n-workflows`:

```powershell
npm.cmd run n8n:sync-templates
```

Start local n8n:

```powershell
.\scripts\run_n8n.cmd
```

Start n8n-mcp:

```powershell
.\scripts\run_n8n_mcp_http.cmd
```

Initialize the local n8n owner account once:

```text
Email: content.factory.local@example.com
Password: ContentFactoryLocal123!
```

Import the content factory workflows:

```powershell
.\scripts\import_content_factory_workflows.ps1
```

The imported workflows are stored in:

```text
workflows/n8n/
```

Imported workflow set:

```text
Content Factory - 01 Topic Discovery
Content Factory - 02 Research Pack
Content Factory - 03 Draft Generator
Content Factory - 04 Quality Gate
Content Factory - 05 Metrics Feedback
Content Factory - 06 Approval Router
Content Factory - 07 Publisher
Content Factory - 08 Document Ingestion
```

The workflow commands call:

```text
scripts\run_content_factory_task.cmd
```

The task wrapper executes:

```text
content_factory_cli.py
```

Useful direct checks:

```powershell
scripts\run_content_factory_task.cmd list-topics --limit 5
scripts\run_content_factory_task.cmd approval-router --limit 10
scripts\run_content_factory_task.cmd ingest-document --topic-id <topic-id> --file data\inbox\sample.md
npm.cmd run n8n:validate-workflows
npm.cmd run n8n:index-templates
```
