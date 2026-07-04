@echo off
setlocal
cd /d "%~dp0.."

set "PYTHON_BIN="
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_BIN=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_BIN if exist ".venv\Scripts\python.exe" set "PYTHON_BIN=%CD%\.venv\Scripts\python.exe"
if not defined PYTHON_BIN if exist ".venv-windows-build\Scripts\python.exe" set "PYTHON_BIN=%CD%\.venv-windows-build\Scripts\python.exe"
if not defined PYTHON_BIN set "PYTHON_BIN=python"

"%PYTHON_BIN%" scripts\index_n8n_workflow_templates.py %*
