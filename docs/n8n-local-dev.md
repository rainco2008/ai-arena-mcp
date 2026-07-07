# n8n Local Development

This project runs n8n through Docker Compose.

## Services

| Service | URL | Purpose |
| --- | --- | --- |
| `contentpilot-web` | `http://localhost:8080` | ContentPilot Next.js admin and proxied API paths |
| `contentpilot` | `http://contentpilot:8080` | Internal Python search, scraping, and task API |
| `n8n` | `http://n8n:5678` | Internal workflow builder and scheduler |

## Start

```powershell
docker compose pull n8n
docker compose up -d --build
```

Default Compose usage exposes only ContentPilot on `localhost:8080`. Open:

```text
http://localhost:8080
```

If you need the n8n editor directly during workflow development, run n8n with a temporary port mapping or use the local helper script outside Compose.

## Connect n8n to this project's API

From inside n8n, call the search/scraping service by Docker service name:

```text
http://contentpilot:8080/api/scrape
http://contentpilot:8080/v1/chat/completions
```

ContentPilot data lives in Postgres/pgvector. n8n should call the internal ContentPilot API instead of reading a local SQLite file.

## API key

n8n API integrations require an API key.

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

The production compose exposes n8n through Caddy at `N8N_DOMAIN`. The ContentPilot web service uses internal `N8N_API_URL=http://n8n:5678` for API calls, and `N8N_WEB_URL` only for the browser-facing editor link.

## npm fallback

If Docker is not installed, use the npm scripts:

```powershell
npm install
npm run n8n
```

Local URLs in npm fallback mode only:

```text
n8n: http://localhost:5678
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
Content Crawl - 01 Discover URLs
Content Crawl - 02 Fetch Process Embed
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
scripts\run_content_factory_task.cmd crawl-run https://example.com
npm.cmd run n8n:index-templates
```
