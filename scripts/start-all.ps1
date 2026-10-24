$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$napcat = Join-Path (Get-Location) "napcat\launcher.bat"
if (-not (Test-Path $napcat)) {
    $napcat = Join-Path (Get-Location) "napcat\napcat.bat"
}
if (-not (Test-Path $napcat)) {
    throw "找不到 NapCat 启动脚本，请确认 napcat/ 目录已解压"
}

Write-Host "启动 NapCat：$napcat" -ForegroundColor Cyan
Start-Process -FilePath $napcat -WorkingDirectory (Join-Path (Get-Location) "napcat")

Start-Sleep -Seconds 3
Write-Host "启动 qqbot..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "start.ps1")
