@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
if not exist "assets\app_icon.ico" (echo ERROR: assets\app_icon.ico is missing. Run set_app_icon.bat first. & pause & exit /b 2)
if not exist "assets\app_icon_48.png" (echo ERROR: assets\app_icon_48.png is missing. Run set_app_icon.bat first. & pause & exit /b 2)
set "BUILDPY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul && set "BUILDPY=py -3.12"
  if not defined BUILDPY py -3.11 -c "import sys" >nul 2>nul && set "BUILDPY=py -3.11"
)
if not defined BUILDPY (
  echo ERROR: Production source builds are certified with Python 3.11 or 3.12.
  echo Install one of those versions, or use the included GitHub Actions Windows build.
  pause
  exit /b 2
)
if exist .venv-build rmdir /s /q .venv-build
%BUILDPY% -m venv .venv-build
if errorlevel 1 (echo Could not create build environment & pause & exit /b 1)
".venv-build\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 (echo Could not install PyInstaller & pause & exit /b 1)
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "translationCore-AI-Bridge-v0.7.5" ^
  --icon "assets\app_icon.ico" ^
  --add-data "assets;assets" ^
  --add-data "userguide;userguide" ^
  --add-data "paratext_connector;paratext_connector" ^
  --add-data "logos_connector;logos_connector" ^
  launcher.pyw
if errorlevel 1 (echo Build failed & pause & exit /b 1)
echo Build complete. See dist\translationCore-AI-Bridge-v0.7.5\
echo Run docs\WINDOWS_CERTIFICATION_CHECKLIST.md against this exact build before distribution.
if /I not "%~1"=="/nopause" pause
