$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$ps1 = Join-Path $root "scripts\start-hidden.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0)

Register-ScheduledTask -TaskName "qqbot-autostart" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Logon start of NapCat + qqbot (QQ AI companion)" -Force | Out-Null

Write-Host "autostart installed: task qqbot-autostart -> $ps1"
