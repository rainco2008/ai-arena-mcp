import fs from "node:fs";
import path from "node:path";

export type DatabaseRuntimeSettings = {
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
};

const defaultDatabaseSettings: DatabaseRuntimeSettings = {
  host: "192.168.0.46",
  port: 5433,
  database: "contentpilot",
  user: "postgres",
  password: "Postgres2024@#",
};

const settingsPath = path.join(process.cwd(), "data", "runtime-settings.json");

function databaseUrlFromParts(settings: DatabaseRuntimeSettings) {
  const url = new URL(`postgresql://${settings.host}:${settings.port}/${settings.database}`);
  url.username = settings.user;
  url.password = settings.password;
  return url.toString();
}

function partsFromDatabaseUrl(value: string): DatabaseRuntimeSettings | null {
  try {
    const url = new URL(value);
    return {
      host: url.hostname,
      port: Number(url.port || "5432"),
      database: url.pathname.replace(/^\//, "") || defaultDatabaseSettings.database,
      user: decodeURIComponent(url.username || defaultDatabaseSettings.user),
      password: decodeURIComponent(url.password || ""),
    };
  } catch {
    return null;
  }
}

function readRuntimeFile(): { database?: DatabaseRuntimeSettings } {
  try {
    return JSON.parse(fs.readFileSync(settingsPath, "utf-8"));
  } catch {
    return {};
  }
}

export function getDatabaseRuntimeSettings() {
  const saved = readRuntimeFile().database;
  if (saved) {
    return {
      source: "Settings page",
      settings: saved,
      connectionString: databaseUrlFromParts(saved),
    };
  }

  const envUrl = process.env.CONTENTPILOT_DATABASE_URL || process.env.CONTENT_FACTORY_DATABASE_URL;
  const envSettings = envUrl ? partsFromDatabaseUrl(envUrl) : null;
  if (envUrl && envSettings) {
    return {
      source: process.env.CONTENTPILOT_DATABASE_URL ? "CONTENTPILOT_DATABASE_URL" : "CONTENT_FACTORY_DATABASE_URL",
      settings: envSettings,
      connectionString: envUrl,
    };
  }

  return {
    source: "built-in default",
    settings: defaultDatabaseSettings,
    connectionString: databaseUrlFromParts(defaultDatabaseSettings),
  };
}

export function saveDatabaseRuntimeSettings(settings: DatabaseRuntimeSettings) {
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
  const current = readRuntimeFile();
  fs.writeFileSync(settingsPath, JSON.stringify({ ...current, database: settings }, null, 2), "utf-8");
}

export function maskedConnectionString(value: string) {
  try {
    const url = new URL(value);
    if (url.password) url.password = "****";
    return url.toString();
  } catch {
    return value.replace(/:\/\/([^:@]+):([^@]+)@/, "://$1:****@");
  }
}
