@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Bitte zuerst 1_installieren_windows.bat ausfuehren.
  pause
  exit /b 1
)
echo Sende eine Knuffelwuff-Testmail...
.venv\Scripts\python.exe bot.py --test-knuffelwuff
if errorlevel 1 (
  echo.
  echo Der Knuffelwuff-E-Mail-Test ist fehlgeschlagen. Pruefe die Angaben in .env.
) else (
  echo.
  echo Test erfolgreich. Bitte Posteingang und Spam-Ordner pruefen.
)
pause
