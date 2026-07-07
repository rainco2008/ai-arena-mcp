"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { randomUUID } from "node:crypto";
import { eq, sql } from "drizzle-orm";
import { db } from "./db/client";
import { crawlSites, crawlUrls } from "./db/schema";
import pg from "pg";
import { resetDatabasePool } from "./db/client";
import { saveDatabaseRuntimeSettings, type DatabaseRuntimeSettings } from "./runtime-settings";

const apiBase =
  process.env.CONTENTPILOT_API_URL ||
  process.env.CONTENT_FACTORY_API_URL ||
  "http://127.0.0.1:8081";

export async function runTask(formData: FormData) {
  const task = String(formData.get("task") || "");
  const baseUrl = String(formData.get("base_url") || "").trim();
  const discoverLimit = String(formData.get("discover_limit") || "200");
  const processLimit = String(formData.get("process_limit") || "20");

  const payload: Record<string, string> = {
    task,
    discover_limit: discoverLimit,
    process_limit: processLimit,
  };

  if (task.startsWith("crawl-")) {
    payload.base_url = baseUrl;
  }

  const response = await fetch(`${apiBase}/api/content-factory/task`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(process.env.CONTENTPILOT_ADMIN_TOKEN
        ? { Authorization: `Bearer ${process.env.CONTENTPILOT_ADMIN_TOKEN}` }
        : {}),
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Task failed: ${text}`);
  }

  revalidatePath("/");
  revalidatePath("/tasks");
}

function requiredString(formData: FormData, key: string) {
  const value = String(formData.get(key) || "").trim();
  if (!value) throw new Error(`${key} is required`);
  return value;
}

function splitHostPort(value: string) {
  const trimmed = value.trim();
  const lastColon = trimmed.lastIndexOf(":");
  if (lastColon > -1 && /^\d+$/.test(trimmed.slice(lastColon + 1))) {
    return {
      host: trimmed.slice(0, lastColon),
      port: Number(trimmed.slice(lastColon + 1)),
    };
  }
  return { host: trimmed, port: 5432 };
}

function connectionStringFromSettings(settings: DatabaseRuntimeSettings) {
  const url = new URL(`postgresql://${settings.host}:${settings.port}/${settings.database}`);
  url.username = settings.user;
  url.password = settings.password;
  return url.toString();
}

export async function saveDatabaseSettings(formData: FormData) {
  const hostPort = splitHostPort(requiredString(formData, "host_port"));
  const settings: DatabaseRuntimeSettings = {
    host: hostPort.host,
    port: Number(formData.get("port") || hostPort.port),
    database: requiredString(formData, "database"),
    user: requiredString(formData, "user"),
    password: String(formData.get("password") || ""),
  };

  if (!settings.host || !Number.isFinite(settings.port) || settings.port < 1) {
    throw new Error("Database host or port is invalid");
  }

  const connectionString = connectionStringFromSettings(settings);
  const testPool = new pg.Pool({ connectionString, max: 1 });
  try {
    await testPool.query("select 1");
  } finally {
    await testPool.end();
  }

  saveDatabaseRuntimeSettings(settings);
  resetDatabasePool();
  revalidatePath("/settings");
  revalidatePath("/");
}

function utcNow() {
  return new Date().toISOString();
}

function normalizeBaseUrl(value: string) {
  const raw = value.trim();
  if (!raw) throw new Error("base_url is required");
  const withScheme = raw.includes("://") ? raw : `https://${raw}`;
  const parsed = new URL(withScheme);
  return `${parsed.protocol}//${parsed.host}`.replace(/\/$/, "");
}

function siteIdFromBaseUrl(baseUrl: string) {
  return randomUUID();
}

export async function createSite(formData: FormData) {
  const baseUrl = normalizeBaseUrl(requiredString(formData, "base_url"));
  const parsed = new URL(baseUrl);
  const domain = parsed.host.toLowerCase();
  const name = String(formData.get("name") || domain).trim();
  const allowedDomainsText = String(formData.get("allowed_domains") || domain).trim();
  const allowedDomains = allowedDomainsText
    .split(/[\n,]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  const crawlPolicy = {
    same_domain_only: formData.get("same_domain_only") === "on",
    respect_robots_sitemaps: formData.get("respect_robots_sitemaps") !== "off",
    max_depth: Number(formData.get("max_depth") || 2),
    rate_limit_ms: Number(formData.get("rate_limit_ms") || 1000),
  };
  const ts = utcNow();

  const existing = await db.select({ id: crawlSites.id }).from(crawlSites).where(eq(crawlSites.baseUrl, baseUrl)).limit(1);
  if (existing[0]) {
    await db
      .update(crawlSites)
      .set({
        domain,
        name,
        allowedDomains: JSON.stringify(allowedDomains.length ? allowedDomains : [domain]),
        crawlPolicy: JSON.stringify(crawlPolicy),
        status: "active",
        updatedAt: ts,
      })
      .where(eq(crawlSites.id, existing[0].id));
  } else {
    await db.insert(crawlSites).values({
      id: siteIdFromBaseUrl(baseUrl),
      baseUrl,
      domain,
      name,
      allowedDomains: JSON.stringify(allowedDomains.length ? allowedDomains : [domain]),
      crawlPolicy: JSON.stringify(crawlPolicy),
      status: "active",
      createdAt: ts,
      updatedAt: ts,
    });
  }

  revalidatePath("/");
  revalidatePath("/sites");
  redirect("/sites");
}

export async function updateSiteStatus(formData: FormData) {
  const siteId = requiredString(formData, "site_id");
  const status = requiredString(formData, "status");
  if (!["active", "paused", "blocked"].includes(status)) {
    throw new Error("Invalid site status");
  }
  await db
    .update(crawlSites)
    .set({ status, updatedAt: utcNow() })
    .where(eq(crawlSites.id, siteId));
  revalidatePath("/");
  revalidatePath("/sites");
  revalidatePath(`/sites/${siteId}`);
}

export async function updateUrlStatus(formData: FormData) {
  const ids = formData
    .getAll("url_id")
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  const status = requiredString(formData, "status");
  if (!ids.length) throw new Error("url_id is required");
  if (!["queued", "ignored", "failed"].includes(status)) {
    throw new Error("Invalid URL status");
  }

  for (const id of ids) {
    await db
      .update(crawlUrls)
      .set({
        status,
        attempts: status === "queued" ? 0 : undefined,
        lastError: status === "queued" || status === "ignored" ? null : undefined,
        nextFetchAt: status === "queued" ? null : undefined,
      })
      .where(eq(crawlUrls.id, id));
  }

  revalidatePath("/queue");
  revalidatePath("/sites");
}

type WorkflowTemplateRow = {
  name: string;
  workflow_json: {
    name?: string;
    nodes?: unknown[];
    connections?: Record<string, unknown>;
    settings?: Record<string, unknown>;
  };
};

async function getWorkflowTemplate(templateId: string) {
  const result = await db.execute(sql`
    select name, workflow_json
    from n8n_workflow_templates
    where id = ${templateId}
    limit 1
  `);
  return result.rows[0] as WorkflowTemplateRow | undefined;
}

async function deployViaN8nApi(workflow: WorkflowTemplateRow["workflow_json"]) {
  const apiUrl = (process.env.N8N_API_URL || "http://127.0.0.1:5678").replace(/\/$/, "");
  const apiKey = process.env.N8N_API_KEY;
  let headers: Record<string, string> = { "Content-Type": "application/json" };

  if (apiKey) {
    headers["X-N8N-API-KEY"] = apiKey;
  } else {
    const email = process.env.CONTENT_FACTORY_N8N_EMAIL || "content.factory.local@example.com";
    const password = process.env.CONTENT_FACTORY_N8N_PASSWORD || "ContentFactoryLocal123!";
    const login = await fetch(`${apiUrl}/rest/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emailOrLdapLoginId: email, password }),
      cache: "no-store",
    });
    if (!login.ok) {
      throw new Error(`n8n login failed: ${await login.text()}`);
    }
    const cookie = login.headers.get("set-cookie");
    if (!cookie) {
      throw new Error("n8n login did not return a session cookie");
    }
    headers = { ...headers, Cookie: cookie };
  }

  const payload = {
    name: workflow.name || "Imported template",
    nodes: workflow.nodes || [],
    connections: workflow.connections || {},
    settings: workflow.settings || { executionOrder: "v1" },
  };

  const endpoint = apiKey ? `${apiUrl}/api/v1/workflows` : `${apiUrl}/rest/workflows`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  const body = await response.text();
  if (!response.ok) {
    throw new Error(`n8n API failed: ${body}`);
  }
  return { provider: "n8n-api", payload: body ? JSON.parse(body) : {} };
}

export async function deployWorkflowTemplate(formData: FormData) {
  const templateId = String(formData.get("template_id") || "");
  if (!templateId) {
    throw new Error("template_id is required");
  }

  const template = await getWorkflowTemplate(templateId);
  if (!template) {
    throw new Error(`Template not found: ${templateId}`);
  }

  await deployViaN8nApi(template.workflow_json);

  revalidatePath("/");
}
