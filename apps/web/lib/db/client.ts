import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "./schema";
import { getDatabaseRuntimeSettings } from "../runtime-settings";

declare global {
  // eslint-disable-next-line no-var
  var contentPilotDbRuntime:
    | {
        connectionString: string;
        pool: pg.Pool;
        db: ReturnType<typeof drizzle<typeof schema>>;
      }
    | undefined;
}

function createRuntime(connectionString: string) {
  const pool = new pg.Pool({ connectionString, max: 5 });
  return {
    connectionString,
    pool,
    db: drizzle(pool, { schema }),
  };
}

function getRuntime() {
  const { connectionString } = getDatabaseRuntimeSettings();
  if (!global.contentPilotDbRuntime || global.contentPilotDbRuntime.connectionString !== connectionString) {
    const previous = global.contentPilotDbRuntime;
    global.contentPilotDbRuntime = createRuntime(connectionString);
    if (previous) void previous.pool.end();
  }
  return global.contentPilotDbRuntime;
}

export function getPool() {
  return getRuntime().pool;
}

export function resetDatabasePool() {
  const previous = global.contentPilotDbRuntime;
  global.contentPilotDbRuntime = undefined;
  if (previous) void previous.pool.end();
}

export const db = new Proxy({} as ReturnType<typeof drizzle<typeof schema>>, {
  get(_target, prop, receiver) {
    return Reflect.get(getRuntime().db, prop, receiver);
  },
});
