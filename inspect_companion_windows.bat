@echo off
setlocal
cd /d "%~dp0"
call setup_windows.bat
if errorlevel 1 exit /b %ERRORLEVEL%
set "ROOT=%~1"
if not defined ROOT set /p "ROOT=translationCore folder: "
if not defined ROOT exit /b 2
".venv\Scripts\python.exe" inspect_companion_state.py "%ROOT%"
pause
