@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo translationCore AI Bridge v0.7.4 - Paratext Live Connector
echo Target: Paratext 9.5 (tested target 9.5.110.1)
echo.
echo IMPORTANT: Close Paratext before continuing.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_connector.ps1" -ParatextInstallDir "%~1"
set EC=%ERRORLEVEL%
if not "%~2"=="/nopause" pause
exit /b %EC%
