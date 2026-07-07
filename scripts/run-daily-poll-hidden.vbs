Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File """ & scriptDir & "\run-daily-poll.ps1"""

For Each argument In WScript.Arguments
    command = command & " " & argument
Next

shell.Run command, 0, False
