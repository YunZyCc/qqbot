$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "created .env, fill in OWNER_QQ and DEEPSEEK_API_KEY" -ForegroundColor Yellow
    exit 1
}

uv sync --python 3.12
uv run pytest -q
Write-Host "setup done" -ForegroundColor Green
