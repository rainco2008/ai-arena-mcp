# Content Crawl Workflows

The content acquisition lane is intentionally reduced to two n8n workflows:

```text
Content Crawl - 01 Discover URLs
Content Crawl - 02 Fetch Process Embed
```

Runtime input is one main domain URL. Direct local execution:

```powershell
scripts\run_content_factory_task.cmd crawl-discover https://example.com
scripts\run_content_factory_task.cmd crawl-process https://example.com
scripts\run_content_factory_task.cmd crawl-run https://example.com
```

`crawl-discover` registers the site, reads `robots.txt` sitemap hints, tries common sitemap/feed URLs, parses XML/RSS/Atom links, falls back to homepage internal links, and stores the URL queue in Postgres/pgvector.

`crawl-process` fetches queued pages, stores raw HTML, extracts page metadata, converts HTML to Markdown, creates a concise summary, and stores a summary vector. If the local OpenAI-compatible summary or embedding endpoint is unavailable, deterministic local fallbacks keep the workflow testable offline.

Crawler data is stored in:

```text
crawl_sites
crawl_runs
crawl_sitemaps
crawl_urls
crawl_pages
crawl_page_embeddings
```

Direct verification:

```powershell
scripts\run_content_factory_task.cmd crawl-discover https://example.com --limit 20
```
