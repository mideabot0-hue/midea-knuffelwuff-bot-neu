Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c cd /d """ & projectDir & """ && .venv\Scripts\python.exe bot.py >> bot.log 2>&1"
shell.Run command, 0, False
