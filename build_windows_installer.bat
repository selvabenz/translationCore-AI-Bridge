@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call build_windows_exe.bat /nopause
if errorlevel 1 exit /b 1
set "ISCC="
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo.
  echo ERROR: Inno Setup 6 is not installed on this BUILD computer.
  echo It is only a build-time tool; end-user computers do not need Inno Setup.
  echo Install Inno Setup 6, then rerun this script.
  pause
  exit /b 2
)
"%ISCC%" installer\translationCore-AI-Bridge.iss
if errorlevel 1 (
  echo Installer build failed.
  pause
  exit /b 1
)
echo.
echo Installer ready under dist-installer\
pause
