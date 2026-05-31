<#
.SYNOPSIS
    Developer task shortcuts for Windows / PowerShell.

.DESCRIPTION
    Mirror of the Makefile for contributors on Windows.

.EXAMPLE
    ./tasks.ps1 install-dev
    ./tasks.ps1 test
    ./tasks.ps1 smoke
    ./tasks.ps1 lint
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'install', 'install-dev', 'test', 'smoke', 'run', 'lint', 'format', 'clean')]
    [string]$Task = 'help'
)

$ErrorActionPreference = 'Stop'

function Show-Help {
    Write-Host "Available tasks:`n"
    Write-Host "  install      Install runtime dependencies"
    Write-Host "  install-dev  Install runtime + dev dependencies"
    Write-Host "  test         Run the test suite"
    Write-Host "  smoke        Run one post end-to-end in dry-run"
    Write-Host "  run          Start the scheduler worker"
    Write-Host "  lint         Lint with ruff"
    Write-Host "  format       Auto-format with ruff"
    Write-Host "  clean        Remove caches and generated artifacts"
    Write-Host "`nUsage: ./tasks.ps1 <task>"
}

switch ($Task) {
    'install'     { python -m pip install -r requirements.txt }
    'install-dev' { python -m pip install -r requirements-dev.txt }
    'test'        { python -m pytest }
    'smoke'       { python -m scripts.smoke_test }
    'run'         { python scheduler/cron.py }
    'lint'        { python -m ruff check . }
    'format'      { python -m ruff format .; python -m ruff check --fix . }
    'clean' {
        Get-ChildItem -Path . -Recurse -Directory -Force `
            -Include '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache' |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleaned caches."
    }
    default       { Show-Help }
}
