@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
if "%~1"=="" (
  echo Usage: set_app_icon.bat "C:\path\to\new_icon.png"
  echo.
  echo Recommended: square PNG, at least 512x512, transparent background if desired.
  pause
  exit /b 2
)
set "ICONPY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul && set "ICONPY=py -3.12"
  if not defined ICONPY py -3.11 -c "import sys" >nul 2>nul && set "ICONPY=py -3.11"
)
if not defined ICONPY (
  echo ERROR: Python 3.11 or 3.12 is required on the BUILD computer to change the icon.
  echo End-user computers do NOT need Python.
  pause
  exit /b 2
)
if not exist .venv-icon\Scripts\python.exe (
  %ICONPY% -m venv .venv-icon || exit /b 1
)
".venv-icon\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet --upgrade Pillow
if errorlevel 1 (
  echo ERROR: Could not install the build-time icon tool dependency Pillow.
  pause
  exit /b 1
)
".venv-icon\Scripts\python.exe" tools\set_app_icon.py "%~1"
if errorlevel 1 (pause & exit /b 1)
echo.
echo Icon assets updated. Now run build_windows_exe.bat or build_windows_installer.bat.
pause
