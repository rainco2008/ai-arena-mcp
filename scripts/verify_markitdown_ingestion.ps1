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

New-Item -ItemType Directory -Force data\inbox | Out-Null
Copy-Item -Force examples\content-factory\sample-source.md data\inbox\sample-source.md

$topicId = "markitdown-verify-$(Get-Date -Format yyyyMMddHHmmss)"

& $python content_factory_cli.py --db $DbPath init-db | Out-Host
& $python content_factory_cli.py --db $DbPath seed-topic "markitdown document ingestion" --id $topicId --priority 998 | Out-Host
& $python content_factory_cli.py --db $DbPath ingest-document --topic-id $topicId --file data\inbox\sample-source.md | Out-Host

$checkScript = @"
import json
import sqlite3

conn = sqlite3.connect(r"$DbPath")
conn.row_factory = sqlite3.Row
row = conn.execute(
    """
    select a.id, a.title, length(a.raw_text) as raw_chars, t.status
    from research_assets a
    join topic_pool t on t.id = a.topic_id
    where a.topic_id = ?
    order by a.collected_at desc
    limit 1
    """,
    (r"$topicId",),
).fetchone()
result = {"ok": bool(row and row["raw_chars"] > 100 and row["status"] == "drafting"), "asset": dict(row) if row else None}
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
