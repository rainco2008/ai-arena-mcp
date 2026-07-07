import { defineConfig } from "drizzle-kit";

const databaseUrl =
  process.env.CONTENTPILOT_DATABASE_URL ||
  process.env.CONTENT_FACTORY_DATABASE_URL ||
  "postgresql://postgres:Postgres2024%40%23@192.168.0.46:5433/contentpilot";

export default defineConfig({
  schema: "./apps/web/lib/db/schema.ts",
  out: "./apps/web/drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: databaseUrl,
  },
});
