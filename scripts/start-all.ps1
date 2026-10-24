$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$napcat = Join-Path (Get-Location) "napcat\launcher.bat"
if (-not (Test-Path $napcat)) {
    $napcat = Join-Path (Get-Location) "napcat\napcat.bat"
}
if (-not (Test-Path $napcat)) {
    throw "NapCat launcher not found; unzip napcat/ first"
}

Write-Host "starting NapCat: $napcat" -ForegroundColor Cyan
Start-Process -FilePath $napcat -WorkingDirectory (Join-Path (Get-Location) "napcat")

Start-Sleep -Seconds 3
Write-Host "starting qqbot..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "start.ps1")
