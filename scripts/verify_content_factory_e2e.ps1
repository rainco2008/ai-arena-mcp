param(
  [string]$DbPath = "data\content_factory.sqlite"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$python = $null
$codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $codexPython) {
  $python = $codexPython
} elseif (Test-Path ".venv\Scripts\python.exe") {
  $python = ".venv\Scripts\python.exe"
} else {
  $python = "python"
}

$topic = "content-factory-e2e-$(Get-Date -Format yyyyMMddHHmmss)"

& $python content_factory_cli.py --db $DbPath init-db | Out-Host
& $python content_factory_cli.py --db $DbPath seed-topic $topic --priority 999 | Out-Host
& $python content_factory_cli.py --db $DbPath research --timeout 5 --allow-offline | Out-Host
& $python content_factory_cli.py --db $DbPath draft --channel blog | Out-Host
& $python content_factory_cli.py --db $DbPath quality-gate --min-chars 100 | Out-Host
& $python content_factory_cli.py --db $DbPath approval-router | Out-Host
& $python content_factory_cli.py --db $DbPath publish --allow-manual-placeholder | Out-Host
& $python content_factory_cli.py --db $DbPath metrics-feedback | Out-Host

$checkScript = @"
import json
import sqlite3
from pathlib import Path

db = Path(r"$DbPath")
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
tables = [
    "topic_pool",
    "research_assets",
    "content_items",
    "review_records",
    "publication_records",
    "performance_metrics",
]
counts = {name: conn.execute(f"select count(*) from {name}").fetchone()[0] for name in tables}
latest = conn.execute(
    """
    select c.id, c.status, c.channel, p.url
    from content_items c
    left join publication_records p on p.content_id = c.id
    order by c.created_at desc
    limit 1
    """
).fetchone()
result = {"ok": all(counts[name] > 0 for name in tables), "counts": counts, "latest": dict(latest) if latest else None}
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
"@

$tmp = New-TemporaryFile
Set-Content -LiteralPath $tmp -Value $checkScript -Encoding UTF8
try {
  & $python $tmp
} finally {
  Remove-Item -LiteralPath $tmp -Force
}
