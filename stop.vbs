' Stop NapCat and qqbot silently
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("WScript.Shell")
code = ws.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & base & "\scripts\stop-hidden.ps1""", 0, True)
If code = 0 Then
    MsgBox "qqbot stopped.", 64, "qqbot"
Else
    MsgBox "Something is still running. Check ports 3000/6099/8080.", 48, "qqbot"
End If
