@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo Building translationCore AI Bridge v0.7.4 Paratext connector...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_connector.ps1" -ParatextInstallDir "%~1"
set EC=%ERRORLEVEL%
if not "%~2"=="/nopause" pause
exit /b %EC%
