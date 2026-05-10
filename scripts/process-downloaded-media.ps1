param(
    [string]$MediaDir = "D:\adult-media-flagger\downloaded-media",
    [string]$DbPath = "D:\adult-media-flagger\media_flags.sqlite",
    [string]$ExportPath = "D:\adult-media-flagger\media_flags.jsonl",
    [string]$Llava = "off"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Output "scan_started=$(Get-Date -Format o)"
.\.venv\Scripts\adult-flag.exe --db $DbPath scan $MediaDir
Write-Output "scan_finished=$(Get-Date -Format o)"

Write-Output "process_started=$(Get-Date -Format o)"
.\.venv\Scripts\adult-flag.exe --db $DbPath process --llava $Llava
Write-Output "process_finished=$(Get-Date -Format o)"

Write-Output "export_started=$(Get-Date -Format o)"
.\.venv\Scripts\adult-flag.exe --db $DbPath export $ExportPath
Write-Output "export_finished=$(Get-Date -Format o)"
