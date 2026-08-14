@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Isolate the app from system-level Python path overrides that can break stdlib discovery.
set "PYTHONHOME="
set "PYTHONPATH="

set "BASEPY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul && set "BASEPY=py -3.12"
  if not defined BASEPY py -3.11 -c "import sys" >nul 2>nul && set "BASEPY=py -3.11"
)

if defined TC_REQUIRE_CERTIFIED_PYTHON (
  if not defined BASEPY (
    echo ERROR: Strict Windows production certification requires Python 3.11 or 3.12.
    echo Your previous run used Python 3.14/Tk 9, which emitted interpreter cleanup warnings.
    echo Install 64-bit Python 3.12 from python.org, then delete .venv and run this again.
    exit /b 8
  )
)

rem Source-mode fallback can run on newer Python, but it is not the certified production matrix.
if not defined BASEPY if not defined TC_REQUIRE_CERTIFIED_PYTHON (
  if not errorlevel 1 (
    py -3.13 -c "import sys" >nul 2>nul && set "BASEPY=py -3.13"
    if not defined BASEPY py -3.14 -c "import sys" >nul 2>nul && set "BASEPY=py -3.14"
    if not defined BASEPY py -3 -c "import sys" >nul 2>nul && set "BASEPY=py -3"
  )
  if not defined BASEPY where python >nul 2>nul && set "BASEPY=python"
)
if not defined BASEPY (
  echo ERROR: Python 3 was not found.
  echo Install 64-bit Python 3.11 or 3.12 from python.org.
  exit /b 2
)

rem Reuse .venv only when it matches the selected base major/minor. This prevents an old
rem Python 3.14 venv from surviving after Python 3.12 is installed.
if exist ".venv\Scripts\python.exe" (
  for /f "delims=" %%V in ('".venv\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "VENVVER=%%V"
  for /f "delims=" %%V in ('%BASEPY% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "BASEVER=%%V"
  if /I not "%VENVVER%"=="%BASEVER%" (
    echo Recreating .venv because Python changed from %VENVVER% to %BASEVER%...
    rmdir /s /q .venv
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating isolated local Python environment with: %BASEPY%
  %BASEPY% -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create .venv.
    exit /b 3
  )
)

".venv\Scripts\python.exe" -c "import sys, tkinter; import tc_ai_bridge; print('Python', sys.version.split()[0], '| Tk', tkinter.TkVersion, '| Bridge', tc_ai_bridge.__version__)"
if errorlevel 1 (
  echo ERROR: Local Python environment is incomplete.
  echo Delete the .venv folder and run setup_windows.bat again.
  exit /b 4
)

if defined TC_REQUIRE_CERTIFIED_PYTHON (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)"
  if errorlevel 1 (
    echo ERROR: Certification venv is not Python 3.11/3.12.
    exit /b 9
  )
)
exit /b 0
