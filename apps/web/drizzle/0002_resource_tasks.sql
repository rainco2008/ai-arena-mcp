CREATE TABLE IF NOT EXISTS "resource_tasks" (
	"id" text PRIMARY KEY NOT NULL,
	"task_type" text NOT NULL,
	"status" text NOT NULL,
	"trigger" text,
	"params" jsonb NOT NULL,
	"progress" integer NOT NULL,
	"started_at" text,
	"finished_at" text,
	"elapsed_ms" integer,
	"returncode" integer,
	"error" text,
	"created_at" text NOT NULL,
	"updated_at" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "resource_task_logs" (
	"id" text PRIMARY KEY NOT NULL,
	"task_id" text NOT NULL,
	"stream" text NOT NULL,
	"message" text NOT NULL,
	"created_at" text NOT NULL
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "resource_tasks_status_created_idx" ON "resource_tasks" ("status", "created_at" DESC);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "resource_task_logs_task_created_idx" ON "resource_task_logs" ("task_id", "created_at" ASC);
