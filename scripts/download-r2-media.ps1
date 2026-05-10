param(
    [string]$OutputDir = "D:\adult-media-flagger\downloaded-media",
    [string]$Prefix = "twitter-media",
    [int]$Workers = 8
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$StateDb = Join-Path $OutputDir ".adult-flag-r2-download-$($Prefix -replace '/', '_').sqlite"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Set-Location $RepoRoot

.\.venv\Scripts\adult-flag.exe r2-download $OutputDir `
    --prefix $Prefix `
    --state-db $StateDb `
    --workers $Workers
