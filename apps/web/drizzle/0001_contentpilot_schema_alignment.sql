CREATE TABLE IF NOT EXISTS "review_records" (
	"id" text PRIMARY KEY NOT NULL,
	"content_id" text NOT NULL,
	"reviewer" text,
	"checklist" text,
	"decision" text NOT NULL,
	"comments" text,
	"created_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "performance_metrics" (
	"id" text PRIMARY KEY NOT NULL,
	"content_id" text NOT NULL,
	"channel" text NOT NULL,
	"impressions" integer NOT NULL,
	"clicks" integer NOT NULL,
	"conversions" integer NOT NULL,
	"engagement" integer NOT NULL,
	"raw_metrics" text,
	"collected_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "schema_migrations" (
	"version" integer PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"applied_at" text NOT NULL
);
--> statement-breakpoint
DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1 FROM pg_constraint WHERE conname = 'crawl_sites_base_url_unique'
	) THEN
		ALTER TABLE "crawl_sites" ADD CONSTRAINT "crawl_sites_base_url_unique" UNIQUE("base_url");
	END IF;
	IF NOT EXISTS (
		SELECT 1 FROM pg_constraint WHERE conname = 'research_assets_topic_id_url_unique'
	) THEN
		ALTER TABLE "research_assets" ADD CONSTRAINT "research_assets_topic_id_url_unique" UNIQUE("topic_id", "url");
	END IF;
	IF NOT EXISTS (
		SELECT 1 FROM pg_constraint WHERE conname = 'n8n_workflow_templates_source_path_unique'
	) THEN
		ALTER TABLE "n8n_workflow_templates" ADD CONSTRAINT "n8n_workflow_templates_source_path_unique" UNIQUE("source_path");
	END IF;
END $$;
