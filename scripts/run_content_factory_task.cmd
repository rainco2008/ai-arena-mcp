@echo off
setlocal
cd /d "%~dp0.."

set "PYTHON_BIN="

where python >nul 2>nul
if "%ERRORLEVEL%"=="0" (
  for /f "delims=" %%P in ('where python') do (
    if not defined PYTHON_BIN set "PYTHON_BIN=%%P"
  )
)

if not defined PYTHON_BIN if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_BIN=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON_BIN if exist ".venv\Scripts\python.exe" set "PYTHON_BIN=%CD%\.venv\Scripts\python.exe"
if not defined PYTHON_BIN if exist ".venv-windows-build\Scripts\python.exe" set "PYTHON_BIN=%CD%\.venv-windows-build\Scripts\python.exe"

if not defined PYTHON_BIN (
  echo No Python runtime found. Install Python 3.10+ or create .venv first.
  exit /b 1
)

"%PYTHON_BIN%" content_factory_cli.py %*
