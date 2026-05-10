param(
    [string]$OutputDir = "D:\adult-media-flagger\downloaded-media",
    [string]$Prefix = "twitter-media"
)

$StateDb = Join-Path $OutputDir ".adult-flag-r2-download-$($Prefix -replace '/', '_').sqlite"

if (-not (Test-Path $StateDb)) {
    Write-Output "No download state DB found at $StateDb"
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

.\.venv\Scripts\python.exe -c "import sqlite3, pathlib; db=pathlib.Path(r'$StateDb'); conn=sqlite3.connect(db); rows=conn.execute('select status, count(*), coalesce(sum(size), 0) from downloads group by status order by status').fetchall(); total=sum(r[1] for r in rows); bytes_done=sum(r[2] for r in rows if r[0]=='downloaded'); print(f'state_db={db}'); print(f'tracked={total}'); [print(f'{status}={count} bytes={size}') for status,count,size in rows]; print(f'downloaded_gib={bytes_done/(1024**3):.3f}'); conn.close()"
