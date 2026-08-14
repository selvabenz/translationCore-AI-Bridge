@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: certify_windows.bat "C:\path\to\translationCore"
  echo The folder must contain projects and resources.
  pause
  exit /b 2
)
set "TC_REQUIRE_CERTIFIED_PYTHON=1"
call "%~dp0test_windows.bat" "%~1"
exit /b %ERRORLEVEL%
