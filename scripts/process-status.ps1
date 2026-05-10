param(
    [string]$DbPath = "D:\adult-media-flagger\media_flags.sqlite"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DbPath)) {
    Write-Output "No processing DB found at $DbPath"
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

.\.venv\Scripts\python.exe scripts\process_status.py --db $DbPath
