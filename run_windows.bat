@echo off
setlocal
cd /d "%~dp0"
call setup_windows.bat
if errorlevel 1 (
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m tc_ai_bridge
exit /b 0
