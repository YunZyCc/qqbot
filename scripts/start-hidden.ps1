$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root ".env"))) { throw "missing .env in $root" }

function Test-Port([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

$env:PYTHONPATH = Join-Path $root "src"
$logDir = Join-Path $root "data"
New-Item -ItemType Directory -Force $logDir | Out-Null

# Start NapCat if not already running.
if (-not (Test-Port 6099)) {
    Start-Process -FilePath (Join-Path $root "napcat\napcat.bat") `
        -WorkingDirectory (Join-Path $root "napcat") -WindowStyle Hidden
    Start-Sleep -Seconds 6
}

# Start qqbot if not already running.
if (-not (Test-Port 8080)) {
    Start-Process -FilePath (Join-Path $root ".venv\Scripts\python.exe") `
        -ArgumentList "-m", "qqbot.main" -WorkingDirectory $root -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# Port 3000 opens only after NapCat logs in.
if (-not (Test-Port 3000)) {
    $login = Join-Path $root "login.html"
    if (Test-Path $login) {
        Start-Process $login
        Write-Host "not logged in, opened login page: $login"
    } else {
        Write-Host "not logged in. Start napcat manually and scan the QR code."
    }
} else {
    Write-Host "qqbot is running and logged in"
}
