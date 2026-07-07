import {
  customType,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  unique,
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

const vector = customType<{ data: number[]; driverData: string }>({
  dataType() {
    return "vector";
  },
  toDriver(value) {
    return `[${value.join(",")}]`;
  },
  fromDriver(value) {
    if (Array.isArray(value)) return value.map(Number);
    return String(value)
      .replace(/^\[|\]$/g, "")
      .split(",")
      .filter(Boolean)
      .map(Number);
  },
});

export const crawlSites = pgTable("crawl_sites", {
  id: text("id").primaryKey(),
  baseUrl: text("base_url").notNull(),
  domain: text("domain").notNull(),
  name: text("name"),
  allowedDomains: text("allowed_domains").notNull(),
  crawlPolicy: text("crawl_policy"),
  status: text("status").notNull(),
  lastDiscoveredAt: text("last_discovered_at"),
  lastCrawledAt: text("last_crawled_at"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => ({
  baseUrlUnique: unique().on(table.baseUrl),
}));

export const crawlRuns = pgTable("crawl_runs", {
  id: text("id").primaryKey(),
  siteId: text("site_id").notNull(),
  kind: text("kind").notNull(),
  trigger: text("trigger"),
  status: text("status").notNull(),
  startedAt: text("started_at").notNull(),
  finishedAt: text("finished_at"),
  discoveredCount: integer("discovered_count").notNull(),
  queuedCount: integer("queued_count").notNull(),
  fetchedCount: integer("fetched_count").notNull(),
  failedCount: integer("failed_count").notNull(),
  error: text("error"),
});

export const crawlSitemaps = pgTable(
  "crawl_sitemaps",
  {
    id: text("id").primaryKey(),
    siteId: text("site_id").notNull(),
    sitemapUrl: text("sitemap_url").notNull(),
    kind: text("kind").notNull(),
    status: text("status").notNull(),
    urlCount: integer("url_count").notNull(),
    lastmod: text("lastmod"),
    fetchedAt: text("fetched_at"),
    error: text("error"),
  },
  (table) => ({
    siteSitemapUnique: unique().on(table.siteId, table.sitemapUrl),
  }),
);

export const crawlUrls = pgTable(
  "crawl_urls",
  {
    id: text("id").primaryKey(),
    siteId: text("site_id").notNull(),
    runId: text("run_id"),
    url: text("url").notNull(),
    normalizedUrl: text("normalized_url").notNull(),
    urlHash: text("url_hash").notNull(),
    source: text("source"),
    priority: integer("priority").notNull(),
    status: text("status").notNull(),
    attempts: integer("attempts").notNull(),
    lastError: text("last_error"),
    discoveredAt: text("discovered_at").notNull(),
    nextFetchAt: text("next_fetch_at"),
  },
  (table) => ({
    siteUrlHashUnique: unique().on(table.siteId, table.urlHash),
  }),
);

export const crawlPages = pgTable(
  "crawl_pages",
  {
    id: text("id").primaryKey(),
    siteId: text("site_id").notNull(),
    urlId: text("url_id"),
    url: text("url").notNull(),
    canonicalUrl: text("canonical_url"),
    title: text("title"),
    metaDescription: text("meta_description"),
    language: text("language"),
    author: text("author"),
    publishedAt: text("published_at"),
    modifiedAt: text("modified_at"),
    httpStatus: integer("http_status"),
    contentType: text("content_type"),
    rawHtml: text("raw_html"),
    htmlHash: text("html_hash"),
    markdown: text("markdown"),
    markdownHash: text("markdown_hash"),
    summary: text("summary"),
    summaryModel: text("summary_model"),
    qualityScore: integer("quality_score").notNull(),
    status: text("status").notNull(),
    fetchedAt: text("fetched_at"),
    processedAt: text("processed_at"),
    error: text("error"),
  },
  (table) => ({
    siteUrlUnique: unique().on(table.siteId, table.url),
  }),
);

export const crawlPageEmbeddings = pgTable(
  "crawl_page_embeddings",
  {
    id: text("id").primaryKey(),
    pageId: text("page_id").notNull(),
    sourceField: text("source_field").notNull(),
    provider: text("provider"),
    model: text("model"),
    dimension: integer("dimension"),
    vector: vector("vector"),
    vectorHash: text("vector_hash"),
    createdAt: text("created_at").notNull(),
  },
  (table) => ({
    pageFieldModelUnique: unique().on(table.pageId, table.sourceField, table.model),
    vectorIndex: index("crawl_page_embeddings_vector_hnsw_idx").using(
      "hnsw",
      sql`${table.vector} vector_cosine_ops`
    ),
  }),
);

export const topicPool = pgTable("topic_pool", {
  id: text("id").primaryKey(),
  keyword: text("keyword").notNull(),
  source: text("source"),
  intent: text("intent"),
  priority: integer("priority").notNull(),
  status: text("status").notNull(),
  owner: text("owner"),
  dueAt: text("due_at"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const researchAssets = pgTable("research_assets", {
  id: text("id").primaryKey(),
  topicId: text("topic_id").notNull(),
  url: text("url").notNull(),
  title: text("title"),
  summary: text("summary"),
  quoteSafe: text("quote_safe"),
  reliability: integer("reliability").notNull(),
  rawText: text("raw_text"),
  collectedAt: text("collected_at").notNull(),
}, (table) => ({
  topicUrlUnique: unique().on(table.topicId, table.url),
}));

export const contentItems = pgTable("content_items", {
  id: text("id").primaryKey(),
  topicId: text("topic_id").notNull(),
  channel: text("channel").notNull(),
  outline: text("outline"),
  draft: text("draft"),
  final: text("final"),
  seoTitle: text("seo_title"),
  metaDescription: text("meta_description"),
  status: text("status").notNull(),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const publicationRecords = pgTable("publication_records", {
  id: text("id").primaryKey(),
  contentId: text("content_id").notNull(),
  channel: text("channel").notNull(),
  status: text("status").notNull(),
  url: text("url"),
  response: text("response"),
  publishedAt: text("published_at"),
  createdAt: text("created_at").notNull(),
});

export const reviewRecords = pgTable("review_records", {
  id: text("id").primaryKey(),
  contentId: text("content_id").notNull(),
  reviewer: text("reviewer"),
  checklist: text("checklist"),
  decision: text("decision").notNull(),
  comments: text("comments"),
  createdAt: text("created_at").notNull(),
});

export const performanceMetrics = pgTable("performance_metrics", {
  id: text("id").primaryKey(),
  contentId: text("content_id").notNull(),
  channel: text("channel").notNull(),
  impressions: integer("impressions").notNull(),
  clicks: integer("clicks").notNull(),
  conversions: integer("conversions").notNull(),
  engagement: integer("engagement").notNull(),
  rawMetrics: text("raw_metrics"),
  collectedAt: text("collected_at").notNull(),
});

export const schemaMigrations = pgTable("schema_migrations", {
  version: integer("version").primaryKey(),
  name: text("name").notNull(),
  appliedAt: text("applied_at").notNull(),
});

export const resourceTasks = pgTable("resource_tasks", {
  id: text("id").primaryKey(),
  taskType: text("task_type").notNull(),
  status: text("status").notNull(),
  trigger: text("trigger"),
  params: jsonb("params").notNull(),
  progress: integer("progress").notNull(),
  startedAt: text("started_at"),
  finishedAt: text("finished_at"),
  elapsedMs: integer("elapsed_ms"),
  returncode: integer("returncode"),
  error: text("error"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const resourceTaskLogs = pgTable("resource_task_logs", {
  id: text("id").primaryKey(),
  taskId: text("task_id").notNull(),
  stream: text("stream").notNull(),
  message: text("message").notNull(),
  createdAt: text("created_at").notNull(),
});

export const n8nWorkflowTemplates = pgTable("n8n_workflow_templates", {
  id: text("id").primaryKey(),
  sourceRepo: text("source_repo").notNull(),
  sourcePath: text("source_path").notNull(),
  category: text("category"),
  name: text("name").notNull(),
  nodeCount: integer("node_count").notNull(),
  nodeTypes: jsonb("node_types").notNull(),
  triggers: jsonb("triggers").notNull(),
  searchText: text("search_text").notNull(),
  workflowJson: jsonb("workflow_json").notNull(),
  workflowHash: text("workflow_hash").notNull(),
  importedAt: text("imported_at").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => ({
  sourcePathUnique: unique().on(table.sourcePath),
}));

export const appSettings = pgTable("app_settings", {
  key: text("key").primaryKey(),
  value: text("value"),
  category: text("category").notNull(),
  label: text("label").notNull(),
  description: text("description"),
  secret: integer("secret").notNull(),
  updatedAt: text("updated_at").notNull(),
});
