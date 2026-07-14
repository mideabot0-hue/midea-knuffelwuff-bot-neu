@echo off
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Midea PortaSplit Bot.lnk"
if exist "%LINK%" (
  del "%LINK%"
  echo Autostart wurde entfernt.
) else (
  echo Es wurde kein Autostart-Eintrag gefunden.
)
pause
