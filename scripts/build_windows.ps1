$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $ProjectRoot ".venv-windows-build"
$DistRoot = Join-Path $ProjectRoot "dist"
$AppDist = Join-Path $DistRoot "GeminiSearch"

function Find-Python {
    $candidates = @(
        "python",
        "py"
    )

    foreach ($candidate in $candidates) {
        try {
            $version = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $version) {
                return $candidate
            }
        } catch {}
    }

    return $null
}

function Ensure-Python {
    $python = Find-Python
    if ($python) {
        return $python
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python is not installed and winget is unavailable. Install Python 3.12 manually, then rerun this script."
    }

    Write-Host "Python not found. Installing Python 3.12 with winget..."
    winget install --id Python.Python.3.12 --source winget --silent --accept-package-agreements --accept-source-agreements

    $python = Find-Python
    if (-not $python) {
        throw "Python installation finished, but python is still not available in PATH. Open a new PowerShell window and rerun this script."
    }
    return $python
}

Set-Location $ProjectRoot

$Python = Ensure-Python
Write-Host "Using Python command: $Python"

if (-not (Test-Path $VenvDir)) {
    & $Python -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPip install -e ".[all]"
& $VenvPip install pyinstaller
& (Join-Path $VenvDir "Scripts\scrapling.exe") install

if (Test-Path $AppDist) {
    Remove-Item -Recurse -Force $AppDist
}

& (Join-Path $VenvDir "Scripts\pyinstaller.exe") `
    --onedir `
    --name GeminiSearch `
    --add-data "gemini_search\static;gemini_search\static" `
    desktop_launcher.py

New-Item -ItemType Directory -Force (Join-Path $AppDist "profiles\default") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $AppDist "logs") | Out-Null

Write-Host ""
Write-Host "Build completed."
Write-Host "Run: $AppDist\GeminiSearch.exe"
