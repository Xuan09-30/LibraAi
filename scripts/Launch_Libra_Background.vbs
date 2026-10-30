' ==============================================================================
' Project Libra v10.0 - Stealth Background Startup Runner
' Launches Libra with pythonw.exe and --hidden in stealth mode (0 console popups)
' ==============================================================================
Option Explicit

Dim fso, wsh, scriptDir, projectDir, pythonwPath, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
Set wsh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectDir = fso.GetParentFolderName(scriptDir)

pythonwPath = projectDir & "\venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonwPath) Then
    pythonwPath = "pythonw.exe"
End If

wsh.CurrentDirectory = projectDir
cmd = """" & pythonwPath & """ """ & projectDir & "\ui\gui.py"" --hidden"

wsh.Run cmd, 0, False

Set fso = Nothing
Set wsh = Nothing
