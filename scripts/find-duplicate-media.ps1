param(
    [string]$MediaDir = "D:\adult-media-flagger\downloaded-media",
    [string]$OutputCsv = "D:\adult-media-flagger\duplicate-media.csv",
    [string]$SummaryPath = "D:\adult-media-flagger\duplicate-media-summary.txt",
    [string]$DeletionCsv = "D:\adult-media-flagger\duplicate-media-deletions.csv",
    [string]$R2Prefix = "twitter-media",
    [ValidateSet("first", "shortest-name")]
    [string]$KeepStrategy = "first",
    [switch]$DeleteLocal,
    [switch]$DeleteR2
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $MediaDir)) {
    throw "Media directory not found: $MediaDir"
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

.\.venv\Scripts\python.exe scripts\find_duplicate_media.py `
    --media-dir $MediaDir `
    --output-csv $OutputCsv `
    --summary-path $SummaryPath `
    --deletion-csv $DeletionCsv `
    --r2-prefix $R2Prefix `
    --keep-strategy $KeepStrategy `
    $(if ($DeleteLocal) { "--delete-local" }) `
    $(if ($DeleteR2) { "--delete-r2" })
