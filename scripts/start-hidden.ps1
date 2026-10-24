$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root ".env"))) { throw "missing .env in $root" }

$env:PYTHONPATH = Join-Path $root "src"
$logDir = Join-Path $root "data"
New-Item -ItemType Directory -Force $logDir | Out-Null

$napcatBat = Join-Path $root "napcat\napcat.bat"
$napcatDir = Join-Path $root "napcat"
Start-Process -FilePath $napcatBat -WorkingDirectory $napcatDir -WindowStyle Hidden

Start-Sleep -Seconds 8

$python = Join-Path $root ".venv\Scripts\python.exe"
Start-Process -FilePath $python -ArgumentList "-m", "qqbot.main" -WorkingDirectory $root -WindowStyle Hidden

# 最多等 15 秒看是否登录成功（3000 端口起来即已登录）
$loggedIn = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) {
        $loggedIn = $true
        break
    }
}

if (-not $loggedIn) {
    Start-Process (Join-Path $root "login.html")
    Write-Host "not logged in, opened login.html"
} else {
    Write-Host "already logged in"
}
