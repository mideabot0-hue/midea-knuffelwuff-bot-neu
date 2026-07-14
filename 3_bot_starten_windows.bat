@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Bitte zuerst 1_installieren_windows.bat ausfuehren.
  pause
  exit /b 1
)
echo Der Bot laeuft. Dieses Fenster offen lassen.
echo Beenden mit Strg+C.
.venv\Scripts\python.exe bot.py
pause
