# 把 Ollama 解压到 D 盘、配置模型目录、启动并拉取 bge-m3
# 用法：.\scripts\setup-ollama.ps1
$ErrorActionPreference = "Stop"

$root = "D:\dev\tools"
$zip = Join-Path $root "ollama.zip"
$dir = Join-Path $root "ollama"
$models = Join-Path $dir "models"

if (-not (Test-Path $zip)) {
    throw "找不到 $zip，请先下载 ollama-windows-amd64.zip"
}

if (-not (Test-Path (Join-Path $dir "ollama.exe"))) {
    Write-Host "解压 Ollama 到 $dir ..." -ForegroundColor Cyan
    Expand-Archive -Path $zip -DestinationPath $dir -Force
}

New-Item -ItemType Directory -Force $models | Out-Null

[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $models, "User")
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "127.0.0.1:11434", "User")
$env:OLLAMA_MODELS = $models
$env:OLLAMA_HOST = "127.0.0.1:11434"

$exe = Join-Path $dir "ollama.exe"
Start-Process -FilePath $exe -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Host "拉取 bge-m3（约 1.2GB，首次较慢）..." -ForegroundColor Cyan
& $exe pull bge-m3

Write-Host "验证 embedding ..." -ForegroundColor Cyan
$body = '{"model":"bge-m3","input":"你好"}'
$resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/v1/embeddings" -Method Post `
    -ContentType "application/json" -Body ([Text.Encoding]::UTF8.GetBytes($body))
$dim = $resp.data[0].embedding.Count
Write-Host "bge-m3 就绪，维度 $dim" -ForegroundColor Green
