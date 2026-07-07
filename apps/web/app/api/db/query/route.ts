import { NextResponse } from "next/server";
import { getPool } from "@/lib/db/client";

function dbQueryApiEnabled() {
  return process.env.NODE_ENV !== "production" || process.env.CONTENTPILOT_ENABLE_DB_QUERY_API === "1";
}

function authorized(request: Request) {
  const token = process.env.CONTENTPILOT_DB_QUERY_TOKEN || process.env.CONTENTPILOT_ADMIN_TOKEN;
  if (!token) return process.env.NODE_ENV !== "production";
  return request.headers.get("authorization") === `Bearer ${token}`;
}

function translateSql(sql: string): string {
  // Convert SQLite-specific INSERT OR IGNORE / REPLACE to standard syntax
  let translated = sql.replace(/INSERT OR IGNORE INTO/gi, "INSERT INTO");
  translated = translated.replace(/INSERT OR REPLACE INTO/gi, "INSERT INTO");

  // Translate SQLite ? placeholders to PostgreSQL $1, $2, ...
  let index = 1;
  translated = translated.replace(/\?/g, () => `$${index++}`);

  return translated;
}

function translateUpsert(sql: string): string {
  const upper = sql.toUpperCase();
  if (upper.includes("INSERT INTO CRAWL_SITES")) {
    return sql.replace(
      /VALUES\s*\(\s*\$1\s*,\s*\$2\s*,\s*\$3\s*,\s*\$4\s*,\s*\$5\s*,\s*\$6\s*,\s*'active'\s*,\s*\$7\s*,\s*\$8\s*\)/i,
      "VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8) ON CONFLICT (base_url) DO NOTHING"
    );
  }
  if (upper.includes("INSERT INTO CRAWL_URLS")) {
    return sql.replace(
      /VALUES\s*\(\s*\$1\s*,\s*\$2\s*,\s*\$3\s*,\s*\$4\s*,\s*\$5\s*,\s*\$6\s*,\s*\$7\s*,\s*\$8\s*,\s*'queued'\s*,\s*\$9\s*\)/i,
      "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'queued', $9) ON CONFLICT (site_id, url_hash) DO NOTHING"
    );
  }
  if (upper.includes("INSERT INTO TOPIC_POOL")) {
    if (sql.includes("VALUES ($1, $2, $3, $4, $5, 'new', $6, $7, $8, $9)")) {
      return sql.replace(
        "VALUES ($1, $2, $3, $4, $5, 'new', $6, $7, $8, $9)",
        "VALUES ($1, $2, $3, $4, $5, 'new', $6, $7, $8, $9) ON CONFLICT (id) DO NOTHING"
      );
    }
    return sql.replace(
      "VALUES ($1, $2, 'seed', 'research', $3, 'new', $4, $5)",
      "VALUES ($1, $2, 'seed', 'research', $3, 'new', $4, $5) ON CONFLICT (id) DO NOTHING"
    );
  }

  const upserts: Record<string, string> = {
    RESEARCH_ASSETS: "(topic_id, url)",
    CRAWL_SITEMAPS: "(site_id, sitemap_url)",
    CRAWL_PAGES: "(site_id, url)",
    CRAWL_PAGE_EMBEDDINGS: "(page_id, source_field, model)",
  };

  for (const [table, conflictTarget] of Object.entries(upserts)) {
    if (upper.includes(`INSERT INTO ${table}`)) {
      const match = sql.match(/\(([^)]+)\)/);
      if (match) {
        const columns = match[1].split(",");
        const assignments = columns
          .map((col) => col.trim())
          .filter((col) => col !== "id")
          .map((col) => `${col} = EXCLUDED.${col}`)
          .join(", ");
        return `${sql} ON CONFLICT ${conflictTarget} DO UPDATE SET ${assignments}`;
      }
    }
  }

  if (upper.includes("INSERT INTO SCHEMA_MIGRATIONS")) {
    return `${sql} ON CONFLICT (version) DO NOTHING`;
  }

  return sql;
}

export async function POST(request: Request) {
  try {
    if (!dbQueryApiEnabled()) {
      return NextResponse.json({ error: "Database query API is disabled" }, { status: 404 });
    }

    if (!authorized(request)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { sql, params } = await request.json();

    if (typeof sql !== "string") {
      return NextResponse.json({ error: "Invalid sql query" }, { status: 500 });
    }

    // Translate SQLite placeholders and dialect specifics to Postgres
    let querySql = translateSql(sql);
    querySql = translateUpsert(querySql);

    const res = await getPool().query(querySql, params || []);
    return NextResponse.json({
      rows: res.rows,
      rowCount: res.rowCount,
      command: res.command,
    });
  } catch (error: any) {
    console.error("Database query error:", error);
    return NextResponse.json(
      { error: error.message || "Database execution failed" },
      { status: 500 }
    );
  }
}
