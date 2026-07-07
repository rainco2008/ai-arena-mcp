import { sql } from "drizzle-orm";
import { db } from "@/lib/db/client";

export const dynamic = "force-dynamic";

function safeFileName(value: string) {
  return value
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120) || "n8n-workflow-template";
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await db.execute(sql`
    select name, workflow_json
    from n8n_workflow_templates
    where id = ${id}
    limit 1
  `);
  const row = result.rows[0] as { name: string; workflow_json: unknown } | undefined;

  if (!row) {
    return Response.json({ error: "Template not found" }, { status: 404 });
  }

  return new Response(JSON.stringify(row.workflow_json, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Disposition": `attachment; filename="${safeFileName(row.name)}.json"`,
      "Cache-Control": "no-store",
    },
  });
}
