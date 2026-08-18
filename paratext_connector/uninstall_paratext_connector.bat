@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_connector.ps1" -ParatextInstallDir "%~1"
set EC=%ERRORLEVEL%
if not "%~2"=="/nopause" pause
exit /b %EC%
