@echo off
setlocal
cd /d "%~dp0"
call setup_windows.bat
if errorlevel 1 (
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m tc_ai_bridge %*
if errorlevel 1 pause
