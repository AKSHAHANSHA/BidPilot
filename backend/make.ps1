<#
.SYNOPSIS
    Windows PowerShell equivalent of the Makefile. GNU make is not installed by default on
    Windows, and the documented workflow must work on this machine without extra tooling.

.EXAMPLE
    ./make.ps1 install
    ./make.ps1 check
    ./make.ps1 revision -m "add users"
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Target = 'help',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$Py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Assert-Venv {
    if (-not (Test-Path $Py)) {
        throw "Virtual environment missing. Run: ./make.ps1 venv; ./make.ps1 install"
    }
}

function Invoke-Step {
    param([string]$Label, [string[]]$Arguments)
    Assert-Venv
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Py @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Show-NotYetImplemented {
    param([string]$Phase)
    Write-Host $Phase -ForegroundColor Yellow
    exit 1
}

switch ($Target.ToLowerInvariant()) {
    'help' {
        Write-Host @'
Targets:
  venv              Create the virtual environment with Python 3.12
  install           Install the backend with development dependencies
  up / down / logs  Manage the PostgreSQL and Redis containers
  dev               up + migrate + api
  api               Run the API with autoreload
  worker            Run the background worker (Phase 5)
  migrate           Apply all migrations
  revision -m "..." Autogenerate a migration
  downgrade         Roll back one migration
  seed              Load demo data (Phase 2)
  lint / format / format-check / typecheck
  test              Unit and API tests (no external services)
  test-integration  Tests requiring PostgreSQL and Redis
  test-all          Every test
  eval              Pipeline evaluation (Phase 11)
  openapi           Export artifacts/openapi.json
  check             format-check + lint + typecheck + test
  demo-reset        Reset demo data (Phase 11)
  clean             Remove caches
'@
    }

    'venv' {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 not found. Install it, then retry.' }
        Write-Host 'Created .venv. Next: ./make.ps1 install' -ForegroundColor Green
    }

    'install' {
        Assert-Venv
        & $Py -m pip install --upgrade pip
        & $Py -m pip install -e '.[dev]'
        if ($LASTEXITCODE -ne 0) { throw 'Install failed' }
    }

    'up' { & docker compose up -d postgres redis }
    'down' { & docker compose down }
    'logs' { & docker compose logs -f }

    'dev' {
        & docker compose up -d postgres redis
        Invoke-Step 'alembic upgrade head' @('-m', 'alembic', 'upgrade', 'head')
        Invoke-Step 'uvicorn' @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')
    }

    'api' {
        Invoke-Step 'uvicorn' @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')
    }

    'worker' { Show-NotYetImplemented 'The worker is implemented in Phase 5 (background jobs and progress).' }
    'seed' { Show-NotYetImplemented 'Seeding is implemented in Phase 2 (company profile and evidence).' }
    'eval' { Show-NotYetImplemented 'Evaluation is implemented in Phase 11 (evaluation and polish).' }
    'demo-reset' { Show-NotYetImplemented 'Demo reset is implemented in Phase 11 (evaluation and polish).' }

    'migrate' { Invoke-Step 'alembic upgrade head' @('-m', 'alembic', 'upgrade', 'head') }
    'downgrade' { Invoke-Step 'alembic downgrade -1' @('-m', 'alembic', 'downgrade', '-1') }

    'revision' {
        $message = $null
        for ($i = 0; $i -lt $Rest.Count; $i++) {
            if ($Rest[$i] -eq '-m' -and ($i + 1) -lt $Rest.Count) { $message = $Rest[$i + 1] }
        }
        if (-not $message) { throw 'Usage: ./make.ps1 revision -m "add users"' }
        Invoke-Step 'alembic revision' @('-m', 'alembic', 'revision', '--autogenerate', '-m', $message)
    }

    'lint' { Invoke-Step 'ruff check' @('-m', 'ruff', 'check', '.') }
    'format' { Invoke-Step 'ruff format' @('-m', 'ruff', 'format', '.') }
    'format-check' { Invoke-Step 'ruff format --check' @('-m', 'ruff', 'format', '--check', '.') }
    'typecheck' { Invoke-Step 'mypy' @('-m', 'mypy', 'app') }

    'test' { Invoke-Step 'pytest (unit + api)' @('-m', 'pytest', '-m', 'not integration') }
    'test-integration' { Invoke-Step 'pytest (integration)' @('-m', 'pytest', '-m', 'integration') }
    'test-all' { Invoke-Step 'pytest (all)' @('-m', 'pytest') }

    'openapi' { Invoke-Step 'export openapi' @('scripts/export_openapi.py') }

    'check' {
        Invoke-Step 'ruff format --check' @('-m', 'ruff', 'format', '--check', '.')
        Invoke-Step 'ruff check' @('-m', 'ruff', 'check', '.')
        Invoke-Step 'mypy' @('-m', 'mypy', 'app')
        Invoke-Step 'pytest (unit + api)' @('-m', 'pytest', '-m', 'not integration')
        Write-Host 'check passed' -ForegroundColor Green
    }

    'clean' {
        foreach ($path in @('.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov', '.coverage')) {
            if (Test-Path $path) { Remove-Item -Recurse -Force $path }
        }
    }

    default { throw "Unknown target '$Target'. Run ./make.ps1 help" }
}
