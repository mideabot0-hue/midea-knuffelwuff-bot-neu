@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo Midea + Knuffelwuff Bot - kostenlose Installation
echo ===============================================
echo.
echo Pruefe Internet- und Proxy-Einstellungen ...

rem Manche Windows-Installationen enthalten einen ungueltigen Platzhalter-
rem Proxy wie "proxy:8080". Er wird nur fuer dieses Installationsfenster
rem ignoriert; die Windows-Systemeinstellungen werden nicht veraendert.
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="
set "PIP_PROXY="
set "PIP_EXTRA_INDEX_URL="
set "PIP_TRUSTED_HOST="
rem NUL entspricht unter Windows os.devnull und blendet pip.ini-Dateien aus.
set "PIP_CONFIG_FILE=NUL"
set "PIP_INDEX_URL=https://pypi.org/simple"
set "NO_PROXY=localhost,127.0.0.1"

where py >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden.
  echo Bitte Python 3.11 oder neuer von python.org installieren.
  echo Bei der Installation "Add Python to PATH" aktivieren.
  pause
  exit /b 1
)

if not exist .venv (
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat

rem Ein bereits angelegtes, aber unvollstaendiges virtuelles Environment
rem kann ohne Loeschen erneut verwendet werden.
python -m pip install --disable-pip-version-check --index-url https://pypi.org/simple -r requirements.txt
if errorlevel 1 goto :proxyerror

rem Kein grosser Chromium-Download: Der Bot nutzt zuerst das bereits unter
rem Windows vorhandene Microsoft Edge, alternativ Google Chrome.
python -c "from playwright.sync_api import sync_playwright; print('Playwright wurde erfolgreich installiert.')"
if errorlevel 1 goto :error

if not exist .env copy .env.example .env >nul

echo.
echo Installation abgeschlossen.
echo Der Bot verwendet Microsoft Edge oder Google Chrome auf diesem PC.
echo Jetzt 2_email_einstellungen_oeffnen_windows.bat starten.
pause
exit /b 0

:proxyerror
echo.
echo Installation konnte PyPI nicht erreichen.
echo.
echo 1. Oeffne Windows Einstellungen ^> Netzwerk und Internet ^> Proxy.
echo 2. Deaktiviere "Proxyserver verwenden", falls dort proxy:8080 steht.
echo 3. Lass "Einstellungen automatisch erkennen" aktiviert.
echo 4. Starte diese Datei danach erneut.
echo.
echo In einem Firmennetz bitte nicht deaktivieren, sondern die IT nach dem
echo korrekten Proxy fragen.
pause
exit /b 1

:error
echo.
echo Installation fehlgeschlagen. Die Fehlermeldung steht oberhalb.
pause
exit /b 1
