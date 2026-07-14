@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo Proxy-Diagnose fuer die Bot-Installation
echo ===============================================
echo.
echo Aktive Proxy-Umgebungsvariablen:
set | findstr /I "HTTP_PROXY HTTPS_PROXY ALL_PROXY PIP_PROXY"
if errorlevel 1 echo Keine Proxy-Umgebungsvariable gefunden.

echo.
echo Windows-WinHTTP-Proxy:
netsh winhttp show proxy

echo.
echo pip-Konfiguration:
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m pip config debug
) else (
  py -3 -m pip config debug
)

echo.
echo Bei "proxy:8080" in den Windows-Proxyeinstellungen:
echo Einstellungen ^> Netzwerk und Internet ^> Proxy ^> Proxyserver verwenden AUS.
echo In einem Firmennetz vorher die IT fragen.
pause
