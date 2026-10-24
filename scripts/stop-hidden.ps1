$ErrorActionPreference = "SilentlyContinue"

$ports = 3000, 6099, 8080
$procs = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $ports -contains $_.LocalPort } |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $procs) {
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

# Fallback: kill python / node processes whose command line mentions qq-ai-bot.
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe'" |
    Where-Object { $_.CommandLine -match 'qq-ai-bot' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 1
$left = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $ports -contains $_.LocalPort }
if ($left) { exit 1 } else { exit 0 }
