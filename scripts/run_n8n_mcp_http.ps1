$ErrorActionPreference = "Continue"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

New-Item -ItemType Directory -Force data\logs | Out-Null

$env:AUTH_TOKEN = $env:N8N_MCP_AUTH_TOKEN
if (-not $env:AUTH_TOKEN) {
    $env:AUTH_TOKEN = "local-dev-n8n-mcp-token-change-me-123456"
}

$env:MCP_AUTH_TOKEN = $env:AUTH_TOKEN
$env:MCP_MODE = "http"
$env:N8N_MODE = "true"
$env:N8N_API_URL = if ($env:N8N_API_URL) { $env:N8N_API_URL } else { "http://localhost:5678" }
$env:PORT = if ($env:PORT) { $env:PORT } else { "3000" }
$env:LOG_LEVEL = if ($env:N8N_MCP_LOG_LEVEL) { $env:N8N_MCP_LOG_LEVEL } else { "info" }

node node_modules\n8n-mcp\dist\http-server.js >> data\logs\n8n-mcp.live.log 2>&1
