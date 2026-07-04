param(
  [string]$RepoUrl = "https://github.com/Zie619/n8n-workflows.git",
  [string]$Target = "vendor\n8n-workflows"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (Test-Path $Target) {
  if (Test-Path (Join-Path $Target ".git")) {
    git -C $Target pull --ff-only
  } else {
    Write-Host "Using vendored workflow template snapshot at $Target"
  }
} else {
  New-Item -ItemType Directory -Force (Split-Path $Target) | Out-Null
  git clone --depth 1 $RepoUrl $Target
  $gitDir = Join-Path $Target ".git"
  if (Test-Path $gitDir) {
    Remove-Item -LiteralPath $gitDir -Recurse -Force
  }
}

.\scripts\index_n8n_workflow_templates.cmd
