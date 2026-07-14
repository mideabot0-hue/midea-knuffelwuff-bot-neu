@echo off
cd /d "%~dp0"
if not exist .env (
  if exist .env.example copy .env.example .env >nul
)
notepad.exe .env
