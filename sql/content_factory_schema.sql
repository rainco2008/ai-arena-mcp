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

CREATE INDEX IF NOT EXISTS idx_topic_pool_status ON topic_pool(status);
CREATE INDEX IF NOT EXISTS idx_topic_pool_priority ON topic_pool(priority DESC);
CREATE INDEX IF NOT EXISTS idx_research_assets_topic_id ON research_assets(topic_id);
CREATE INDEX IF NOT EXISTS idx_content_items_topic_id ON content_items(topic_id);
CREATE INDEX IF NOT EXISTS idx_content_items_status ON content_items(status);
CREATE INDEX IF NOT EXISTS idx_review_records_content_id ON review_records(content_id);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_content_id ON performance_metrics(content_id);
CREATE INDEX IF NOT EXISTS idx_publication_records_content_id ON publication_records(content_id);

INSERT OR IGNORE INTO schema_migrations(version, name)
VALUES (1, 'content_factory_initial_schema');
