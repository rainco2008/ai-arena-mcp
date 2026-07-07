-- LEGACY SQLITE SCHEMA.
--
-- ContentPilot's primary schema is now the Drizzle/Postgres schema in:
-- apps/web/lib/db/schema.ts
--
-- Keep this file only for reading or migrating old local SQLite MVP databases.
-- Do not use it to initialize new Postgres environments.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS topic_pool (
  id TEXT PRIMARY KEY,
  keyword TEXT NOT NULL,
  source TEXT,
  intent TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'new',
  owner TEXT,
  due_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK(status IN ('new', 'researching', 'drafting', 'reviewing', 'scheduled', 'published', 'rejected'))
);

CREATE TABLE IF NOT EXISTS research_assets (
  id TEXT PRIMARY KEY,
  topic_id TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  quote_safe TEXT,
  reliability INTEGER NOT NULL DEFAULT 0,
  raw_text TEXT,
  collected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE(topic_id, url),
  FOREIGN KEY(topic_id) REFERENCES topic_pool(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content_items (
  id TEXT PRIMARY KEY,
  topic_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  outline TEXT,
  draft TEXT,
  final TEXT,
  seo_title TEXT,
  meta_description TEXT,
  status TEXT NOT NULL DEFAULT 'drafting',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK(status IN ('drafting', 'reviewing', 'scheduled', 'published', 'rejected')),
  FOREIGN KEY(topic_id) REFERENCES topic_pool(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_records (
  id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL,
  reviewer TEXT,
  checklist TEXT,
  decision TEXT NOT NULL,
  comments TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK(decision IN ('approve', 'request_changes', 'reject')),
  FOREIGN KEY(content_id) REFERENCES content_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS performance_metrics (
  id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  impressions INTEGER NOT NULL DEFAULT 0,
  clicks INTEGER NOT NULL DEFAULT 0,
  conversions INTEGER NOT NULL DEFAULT 0,
  engagement INTEGER NOT NULL DEFAULT 0,
  raw_metrics TEXT,
  collected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  FOREIGN KEY(content_id) REFERENCES content_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publication_records (
  id TEXT PRIMARY KEY,
  content_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  status TEXT NOT NULL,
  url TEXT,
  response TEXT,
  published_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK(status IN ('published', 'failed')),
  FOREIGN KEY(content_id) REFERENCES content_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crawl_sites (
  id TEXT PRIMARY KEY,
  base_url TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  name TEXT,
  allowed_domains TEXT NOT NULL,
  crawl_policy TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  last_discovered_at TEXT,
  last_crawled_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK(status IN ('active', 'paused', 'blocked'))
);

CREATE TABLE IF NOT EXISTS crawl_runs (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  trigger TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  finished_at TEXT,
  discovered_count INTEGER NOT NULL DEFAULT 0,
  queued_count INTEGER NOT NULL DEFAULT 0,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  CHECK(kind IN ('discover', 'process')),
  CHECK(status IN ('running', 'succeeded', 'failed')),
  FOREIGN KEY(site_id) REFERENCES crawl_sites(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crawl_sitemaps (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  sitemap_url TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'xml',
  status TEXT NOT NULL DEFAULT 'new',
  url_count INTEGER NOT NULL DEFAULT 0,
  lastmod TEXT,
  fetched_at TEXT,
  error TEXT,
  UNIQUE(site_id, sitemap_url),
  FOREIGN KEY(site_id) REFERENCES crawl_sites(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crawl_urls (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  run_id TEXT,
  url TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  source TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  discovered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  next_fetch_at TEXT,
  UNIQUE(site_id, url_hash),
  CHECK(status IN ('queued', 'processing', 'fetched', 'failed', 'ignored', 'duplicate')),
  FOREIGN KEY(site_id) REFERENCES crawl_sites(id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES crawl_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS crawl_pages (
  id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  url_id TEXT,
  url TEXT NOT NULL,
  canonical_url TEXT,
  title TEXT,
  meta_description TEXT,
  language TEXT,
  author TEXT,
  published_at TEXT,
  modified_at TEXT,
  http_status INTEGER,
  content_type TEXT,
  raw_html TEXT,
  html_hash TEXT,
  markdown TEXT,
  markdown_hash TEXT,
  summary TEXT,
  summary_model TEXT,
  quality_score INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'fetched',
  fetched_at TEXT,
  processed_at TEXT,
  error TEXT,
  UNIQUE(site_id, url),
  FOREIGN KEY(site_id) REFERENCES crawl_sites(id) ON DELETE CASCADE,
  FOREIGN KEY(url_id) REFERENCES crawl_urls(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS crawl_page_embeddings (
  id TEXT PRIMARY KEY,
  page_id TEXT NOT NULL,
  source_field TEXT NOT NULL DEFAULT 'summary',
  provider TEXT,
  model TEXT,
  dimension INTEGER,
  vector TEXT,
  vector_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE(page_id, source_field, model),
  FOREIGN KEY(page_id) REFERENCES crawl_pages(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_topic_pool_status ON topic_pool(status);
CREATE INDEX IF NOT EXISTS idx_topic_pool_priority ON topic_pool(priority DESC);
CREATE INDEX IF NOT EXISTS idx_research_assets_topic_id ON research_assets(topic_id);
CREATE INDEX IF NOT EXISTS idx_content_items_topic_id ON content_items(topic_id);
CREATE INDEX IF NOT EXISTS idx_content_items_status ON content_items(status);
CREATE INDEX IF NOT EXISTS idx_review_records_content_id ON review_records(content_id);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_content_id ON performance_metrics(content_id);
CREATE INDEX IF NOT EXISTS idx_publication_records_content_id ON publication_records(content_id);
CREATE INDEX IF NOT EXISTS idx_crawl_sites_domain ON crawl_sites(domain);
CREATE INDEX IF NOT EXISTS idx_crawl_runs_site_kind ON crawl_runs(site_id, kind, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_sitemaps_site ON crawl_sitemaps(site_id);
CREATE INDEX IF NOT EXISTS idx_crawl_urls_site_status ON crawl_urls(site_id, status, priority DESC, discovered_at ASC);
CREATE INDEX IF NOT EXISTS idx_crawl_pages_site_url ON crawl_pages(site_id, url);
CREATE INDEX IF NOT EXISTS idx_crawl_embeddings_page ON crawl_page_embeddings(page_id);

INSERT OR IGNORE INTO schema_migrations(version, name)
VALUES (1, 'content_factory_initial_schema');
