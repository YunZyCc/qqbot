' 静默停止 NapCat + qqbot
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("WScript.Shell")
code = ws.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & base & "\scripts\stop-hidden.ps1""", 0, True)
If code = 0 Then
    MsgBox "小毒已停止。", 64, "qqbot"
Else
    MsgBox "停止时遇到问题，可能有进程仍在运行。", 48, "qqbot"
End If
