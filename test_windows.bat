@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
call setup_windows.bat
if errorlevel 1 (
  echo TEST SETUP FAILED
  pause
  exit /b 1
)

set "LIVE_TC_ROOT=%~1"
if not defined LIVE_TC_ROOT if defined TC_TEST_ROOT_SAVED set "LIVE_TC_ROOT=%TC_TEST_ROOT_SAVED%"

if not defined LIVE_TC_ROOT (
  echo.
  echo OPTIONAL REAL-DATA CERTIFICATION
  echo Enter the translationCore DATA folder that contains "projects" and "resources".
  echo Example: C:\path\to\translationCore
  echo Press ENTER to run portable production tests only.
  set /p "LIVE_TC_ROOT=translationCore folder: "
)

set "BACKEND_MODE=portable"
set "CERT_PARENT="
set "CERT_ROOT="
if defined LIVE_TC_ROOT (
  for %%I in ("!LIVE_TC_ROOT!") do set "LIVE_TC_ROOT=%%~fI"
  if not exist "!LIVE_TC_ROOT!\projects" (
    if exist "!LIVE_TC_ROOT!\translationCore\projects" set "LIVE_TC_ROOT=!LIVE_TC_ROOT!\translationCore"
  )
  if not exist "!LIVE_TC_ROOT!\projects" (
    echo.
    echo ERROR: "!LIVE_TC_ROOT!" does not contain a projects folder.
    pause
    exit /b 5
  )
  if not exist "!LIVE_TC_ROOT!\resources" (
    echo.
    echo ERROR: "!LIVE_TC_ROOT!" does not contain a resources folder.
    pause
    exit /b 6
  )

  rem CRITICAL: never run write-capable certification directly on the user's live projects.
  set "CERT_PARENT=%TEMP%\tc_ai_bridge_v073_cert_!RANDOM!_!RANDOM!"
  set "CERT_ROOT=!CERT_PARENT!\translationCore"

  if not defined CERT_ROOT (
    echo ERROR: Internal safety failure: disposable certification path is empty.
    exit /b 11
  )
  if /I "!CERT_ROOT!"=="%CD%" (
    echo ERROR: Internal safety failure: disposable path resolved to the application directory.
    exit /b 12
  )
  if /I "!CERT_ROOT!"=="!LIVE_TC_ROOT!" (
    echo ERROR: Internal safety failure: disposable path resolved to the LIVE backend.
    exit /b 13
  )

  echo.
  echo Preparing disposable certification clone...
  echo LIVE PROJECTS:         !LIVE_TC_ROOT!
  echo DISPOSABLE TEST COPY:  !CERT_ROOT!
  echo.
  ".venv\Scripts\python.exe" "tests\certification_fixture.py" "!LIVE_TC_ROOT!" "!CERT_ROOT!"
  if errorlevel 1 (
    echo ERROR: Could not prepare disposable certification fixture.
    if defined CERT_PARENT if exist "!CERT_PARENT!" rmdir /s /q "!CERT_PARENT!" >nul 2>nul
    pause
    exit /b 7
  )
  if not exist "!CERT_ROOT!\projects" (
    echo ERROR: Safety verification failed: disposable projects folder was not created.
    if exist "!CERT_PARENT!" rmdir /s /q "!CERT_PARENT!" >nul 2>nul
    pause
    exit /b 14
  )
  if not exist "!CERT_ROOT!\resources" (
    echo ERROR: Safety verification failed: disposable resources link was not created.
    if exist "!CERT_PARENT!" rmdir /s /q "!CERT_PARENT!" >nul 2>nul
    pause
    exit /b 15
  )

  set "TC_TEST_ROOT=!CERT_ROOT!"
  set "TC_TEST_SOURCE_ROOT=!LIVE_TC_ROOT!"
  set "BACKEND_MODE=real"
  echo.
  echo VERIFIED LIVE PROJECTS:        !LIVE_TC_ROOT!
  echo VERIFIED DISPOSABLE TEST COPY: !CERT_ROOT!
  echo All write-capable tests run ONLY against the disposable copy.
) else (
  set "TC_TEST_ROOT=__missing_real_backend_fixture__"
  echo Running portable production suite. Real-backend tests will be reported as SKIPPED.
)

echo.
echo Running translationCore AI Bridge v0.7.5 regression tests...
".venv\Scripts\python.exe" "tests\run_windows_certification.py"
set "TEST_RC=!ERRORLEVEL!"

rem Remove the resources junction first, then the disposable project clone. Never delete LIVE_TC_ROOT.
if defined CERT_ROOT if exist "!CERT_ROOT!\resources" rmdir "!CERT_ROOT!\resources" >nul 2>nul
if defined CERT_PARENT if exist "!CERT_PARENT!" rmdir /s /q "!CERT_PARENT!" >nul 2>nul

echo.
if not "!TEST_RC!"=="0" (
  echo TESTS FAILED
  echo Your live translationCore projects were NOT used as write targets by v0.7.5 certification.
  pause
  exit /b !TEST_RC!
)

if /I "!BACKEND_MODE!"=="real" (
  echo PORTABLE + REAL-BACKEND TESTS PASSED ON A DISPOSABLE CLONE.
  echo Your live translationCore project folder was not used for write-capable tests.
  echo Continue with docs\WINDOWS_CERTIFICATION_CHECKLIST.md for packaged-EXE certification.
) else (
  echo PORTABLE TESTS PASSED.
  echo NOTE: Real translationCore backend tests were intentionally skipped because no backend path was supplied.
  echo Re-run: test_windows.bat "C:\path\to\translationCore"
)
pause
exit /b 0
