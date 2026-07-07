@echo off
setlocal
cd /d "%~dp0\.."
set GEMINI_SEARCH_SKIP_ENGINE_START=1
"%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m gemini_search --host 127.0.0.1 --port 8081
