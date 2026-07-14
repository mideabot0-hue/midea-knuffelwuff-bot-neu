@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Bitte zuerst 1_installieren_windows.bat ausfuehren.
  pause
  exit /b 1
)
echo Pruefe Midea und Knuffelwuff ohne E-Mail-Versand...
.venv\Scripts\python.exe bot.py --once --dry-run --verbose
pause
