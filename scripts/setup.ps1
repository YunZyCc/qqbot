$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已生成 .env，请先填写 OWNER_QQ 和 DEEPSEEK_API_KEY" -ForegroundColor Yellow
    exit 1
}

uv sync --python 3.12
uv run pytest -q
Write-Host "环境准备完成" -ForegroundColor Green
