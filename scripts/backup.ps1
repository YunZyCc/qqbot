$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$data = Join-Path (Get-Location) "data"
$backup = Join-Path $data "backup"
New-Item -ItemType Directory -Force $backup | Out-Null

$db = Join-Path $data "qqbot.db"
if (-not (Test-Path $db)) {
    Write-Host "database not found, skip backup"
    exit 0
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$target = Join-Path $backup "qqbot_$stamp.db"
& ".\.venv\Scripts\python.exe" -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" $db $target
Write-Host "backed up to $target"

Get-ChildItem $backup -Filter "qqbot_*.db" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force -ErrorAction SilentlyContinue
