$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $projectDir "start_bot_hidden.vbs"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Midea PortaSplit Bot.lnk"

$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $projectDir
$shortcut.Description = "Startet den kostenlosen Midea-PortaSplit-Verfuegbarkeitsbot"
$shortcut.Save()

Write-Host "Autostart wurde eingerichtet."
Write-Host "Der Bot startet kuenftig nach der Windows-Anmeldung im Hintergrund."
Write-Host "Protokoll: $projectDir\bot.log"
Read-Host "Enter druecken zum Beenden"
