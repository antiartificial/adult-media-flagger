param(
    [string]$DbPath = "D:\adult-media-flagger\media_flags.sqlite",
    [string]$ExportPath = "D:\adult-media-flagger\media_flags.jsonl",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$argsList = @("scripts\reconcile_db.py", "--db", $DbPath)
if ($DryRun) {
    $argsList += "--dry-run"
}

.\.venv\Scripts\python.exe @argsList

if (-not $DryRun) {
    .\.venv\Scripts\adult-flag.exe --db $DbPath export $ExportPath
}
