@echo off
setlocal
cd /d "%~dp0.."

if not exist data\n8n-local mkdir data\n8n-local
if not exist data\logs mkdir data\logs

set "N8N_USER_FOLDER=%CD%\data\n8n-local"
set "N8N_RUNNERS_ENABLED=true"
set "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false"
set "GENERIC_TIMEZONE=Europe/London"
set "TZ=Europe/London"
set "N8N_HOST=localhost"
set "N8N_PORT=5678"
set "N8N_PROTOCOL=http"
set "N8N_SECURE_COOKIE=false"

node node_modules\n8n\bin\n8n start >> data\logs\n8n.live.log 2>&1
