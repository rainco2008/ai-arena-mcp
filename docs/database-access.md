# Database Access Notes

The app uses Postgres as the active ContentPilot database. The local
`data/content_factory.sqlite` file was legacy/local data and should not be used
as the source of truth for the template library.

## Default Database

The default connection is defined in `content_factory/db.py` and
`apps/web/lib/runtime-settings.ts`:

```text
postgresql://postgres:Postgres2024%40%23@192.168.0.46:5433/contentpilot
```

If `data/runtime-settings.json`, `CONTENTPILOT_DATABASE_URL`, or
`CONTENT_FACTORY_DATABASE_URL` is present, those values can override the built-in
default.

## Query Method Used

Use the repository's existing Node dependency `pg` from `node_modules`.
PowerShell inline quoting can break SQL strings, so pass the JavaScript through a
PowerShell here-string:

```powershell
$code = @'
const { Client } = require('pg');
const url = 'postgresql://postgres:Postgres2024%40%23@192.168.0.46:5433/contentpilot';

(async () => {
  const c = new Client({ connectionString: url });
  await c.connect();

  const pattern = '%playwright%';
  const where = 'search_text ilike $1 or workflow_json::text ilike $1 or name ilike $1 or source_path ilike $1';

  const count = await c.query(
    'select count(1)::int as total, count(1) filter (where ' + where + ')::int as playwright_matches from n8n_workflow_templates',
    [pattern],
  );
  console.log(JSON.stringify(count.rows, null, 2));

  const rows = await c.query(
    'select id,name,category,source_path,node_count,node_types,triggers from n8n_workflow_templates where ' + where + ' order by name limit 50',
    [pattern],
  );
  console.log(JSON.stringify(rows.rows, null, 2));

  await c.end();
})().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
'@
node -e $code
```

In the Codex sandbox, connecting to `192.168.0.46:5433` may fail with
`connect EACCES`. Re-run the same read-only command with escalated permissions
when querying the LAN Postgres database.

## Template Table

The n8n template library is stored in:

```text
n8n_workflow_templates
```

Useful columns include:

```text
id, name, category, source_path, node_count, node_types, triggers, search_text, workflow_json
```
