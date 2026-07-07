import { saveDatabaseSettings } from "@/lib/actions";
import { db } from "@/lib/db/client";
import { getDatabaseRuntimeSettings } from "@/lib/runtime-settings";
import { sql } from "drizzle-orm";
import { PasswordInput } from "./password-input";

export const dynamic = "force-dynamic";

type CurrentConnection = {
  database: string;
  user: string;
  host: string | null;
  port: number | null;
};

async function currentConnection() {
  try {
    const result = await db.execute(sql`
      select
        current_database() as database,
        current_user as user,
        inet_server_addr()::text as host,
        inet_server_port()::int as port
    `);
    return { row: result.rows[0] as CurrentConnection, error: null };
  } catch (error) {
    return {
      row: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

export default async function SettingsPage() {
  const runtime = getDatabaseRuntimeSettings();
  const { row, error } = await currentConnection();
  const settings = runtime.settings;

  return (
    <section className="panel settingsPanel">
      <h1>Settings</h1>
      <p className="panelSub">Runtime connection and workflow integration configuration.</p>

      {error ? (
        <section className="notice">
          <strong>Database unavailable</strong>
          <span>{error}</span>
        </section>
      ) : null}

      <section className="settingsStatus">
        <strong>{row ? "Database connected" : "Database not connected"}</strong>
        <span>
          {row
            ? `${row.database} as ${row.user}`
            : "Update the connection below and save after testing."}
        </span>
      </section>

      <form action={saveDatabaseSettings} className="settingsForm">
        <h2>Database Connection</h2>
        <div className="settingsField">
          <label htmlFor="database-host">Host</label>
          <input id="database-host" name="host_port" defaultValue={`${settings.host}:${settings.port}`} placeholder="192.168.0.46:5433" />
        </div>
        <div className="settingsField">
          <label htmlFor="database-name">Database</label>
          <input id="database-name" name="database" defaultValue={settings.database} placeholder="contentpilot" />
        </div>
        <div className="settingsField">
          <label htmlFor="database-user">Superuser</label>
          <input id="database-user" name="user" defaultValue={settings.user} placeholder="postgres" />
        </div>
        <div className="settingsField">
          <label htmlFor="database-password">Password</label>
          <PasswordInput defaultValue={settings.password} />
        </div>
        <button type="submit">Save and Test Connection</button>
      </form>
    </section>
  );
}
