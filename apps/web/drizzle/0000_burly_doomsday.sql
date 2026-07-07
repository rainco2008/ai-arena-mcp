CREATE TABLE "app_settings" (
	"key" text PRIMARY KEY NOT NULL,
	"value" text,
	"category" text NOT NULL,
	"label" text NOT NULL,
	"description" text,
	"secret" integer NOT NULL,
	"updated_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "content_items" (
	"id" text PRIMARY KEY NOT NULL,
	"topic_id" text NOT NULL,
	"channel" text NOT NULL,
	"outline" text,
	"draft" text,
	"final" text,
	"seo_title" text,
	"meta_description" text,
	"status" text NOT NULL,
	"created_at" text NOT NULL,
	"updated_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "crawl_page_embeddings" (
	"id" text PRIMARY KEY NOT NULL,
	"page_id" text NOT NULL,
	"source_field" text NOT NULL,
	"provider" text,
	"model" text,
	"dimension" integer,
	"vector" vector,
	"vector_hash" text,
	"created_at" text NOT NULL,
	CONSTRAINT "crawl_page_embeddings_page_id_source_field_model_unique" UNIQUE("page_id","source_field","model")
);
--> statement-breakpoint
CREATE TABLE "crawl_pages" (
	"id" text PRIMARY KEY NOT NULL,
	"site_id" text NOT NULL,
	"url_id" text,
	"url" text NOT NULL,
	"canonical_url" text,
	"title" text,
	"meta_description" text,
	"language" text,
	"author" text,
	"published_at" text,
	"modified_at" text,
	"http_status" integer,
	"content_type" text,
	"raw_html" text,
	"html_hash" text,
	"markdown" text,
	"markdown_hash" text,
	"summary" text,
	"summary_model" text,
	"quality_score" integer NOT NULL,
	"status" text NOT NULL,
	"fetched_at" text,
	"processed_at" text,
	"error" text,
	CONSTRAINT "crawl_pages_site_id_url_unique" UNIQUE("site_id","url")
);
--> statement-breakpoint
CREATE TABLE "crawl_runs" (
	"id" text PRIMARY KEY NOT NULL,
	"site_id" text NOT NULL,
	"kind" text NOT NULL,
	"trigger" text,
	"status" text NOT NULL,
	"started_at" text NOT NULL,
	"finished_at" text,
	"discovered_count" integer NOT NULL,
	"queued_count" integer NOT NULL,
	"fetched_count" integer NOT NULL,
	"failed_count" integer NOT NULL,
	"error" text
);
--> statement-breakpoint
CREATE TABLE "crawl_sitemaps" (
	"id" text PRIMARY KEY NOT NULL,
	"site_id" text NOT NULL,
	"sitemap_url" text NOT NULL,
	"kind" text NOT NULL,
	"status" text NOT NULL,
	"url_count" integer NOT NULL,
	"lastmod" text,
	"fetched_at" text,
	"error" text,
	CONSTRAINT "crawl_sitemaps_site_id_sitemap_url_unique" UNIQUE("site_id","sitemap_url")
);
--> statement-breakpoint
CREATE TABLE "crawl_sites" (
	"id" text PRIMARY KEY NOT NULL,
	"base_url" text NOT NULL,
	"domain" text NOT NULL,
	"name" text,
	"allowed_domains" text NOT NULL,
	"crawl_policy" text,
	"status" text NOT NULL,
	"last_discovered_at" text,
	"last_crawled_at" text,
	"created_at" text NOT NULL,
	"updated_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "crawl_urls" (
	"id" text PRIMARY KEY NOT NULL,
	"site_id" text NOT NULL,
	"run_id" text,
	"url" text NOT NULL,
	"normalized_url" text NOT NULL,
	"url_hash" text NOT NULL,
	"source" text,
	"priority" integer NOT NULL,
	"status" text NOT NULL,
	"attempts" integer NOT NULL,
	"last_error" text,
	"discovered_at" text NOT NULL,
	"next_fetch_at" text,
	CONSTRAINT "crawl_urls_site_id_url_hash_unique" UNIQUE("site_id","url_hash")
);
--> statement-breakpoint
CREATE TABLE "n8n_workflow_templates" (
	"id" text PRIMARY KEY NOT NULL,
	"source_repo" text NOT NULL,
	"source_path" text NOT NULL,
	"category" text,
	"name" text NOT NULL,
	"node_count" integer NOT NULL,
	"node_types" jsonb NOT NULL,
	"triggers" jsonb NOT NULL,
	"search_text" text NOT NULL,
	"workflow_json" jsonb NOT NULL,
	"workflow_hash" text NOT NULL,
	"imported_at" text NOT NULL,
	"updated_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "publication_records" (
	"id" text PRIMARY KEY NOT NULL,
	"content_id" text NOT NULL,
	"channel" text NOT NULL,
	"status" text NOT NULL,
	"url" text,
	"response" text,
	"published_at" text,
	"created_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "research_assets" (
	"id" text PRIMARY KEY NOT NULL,
	"topic_id" text NOT NULL,
	"url" text NOT NULL,
	"title" text,
	"summary" text,
	"quote_safe" text,
	"reliability" integer NOT NULL,
	"raw_text" text,
	"collected_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "topic_pool" (
	"id" text PRIMARY KEY NOT NULL,
	"keyword" text NOT NULL,
	"source" text,
	"intent" text,
	"priority" integer NOT NULL,
	"status" text NOT NULL,
	"owner" text,
	"due_at" text,
	"created_at" text NOT NULL,
	"updated_at" text NOT NULL
);
--> statement-breakpoint
CREATE INDEX "crawl_page_embeddings_vector_hnsw_idx" ON "crawl_page_embeddings" USING hnsw ("vector" vector_cosine_ops);