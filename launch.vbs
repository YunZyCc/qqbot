' 无窗口启动 NapCat + qqbot，未登录时自动打开扫码页
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("WScript.Shell")
ws.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & base & "\scripts\start-hidden.ps1""", 0, False
