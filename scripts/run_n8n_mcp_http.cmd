@echo off
setlocal
cd /d "%~dp0.."

if not exist data\logs mkdir data\logs

if "%N8N_MCP_AUTH_TOKEN%"=="" (
  set "AUTH_TOKEN=local-dev-n8n-mcp-token-change-me-123456"
) else (
  set "AUTH_TOKEN=%N8N_MCP_AUTH_TOKEN%"
)

set "MCP_AUTH_TOKEN=%AUTH_TOKEN%"
set "MCP_MODE=http"
set "N8N_MODE=true"
if "%N8N_API_URL%"=="" set "N8N_API_URL=http://localhost:5678"
if "%PORT%"=="" set "PORT=3000"
if "%N8N_MCP_LOG_LEVEL%"=="" (
  set "LOG_LEVEL=info"
) else (
  set "LOG_LEVEL=%N8N_MCP_LOG_LEVEL%"
)

node node_modules\n8n-mcp\dist\http-server.js >> data\logs\n8n-mcp.live.log 2>&1
