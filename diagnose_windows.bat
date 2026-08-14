@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
echo translationCore AI Bridge v0.7.0 Windows diagnostics
echo =====================================================
echo Current folder: %CD%
echo.
where py 2>nul
py -0p 2>nul
echo.
call setup_windows.bat
if errorlevel 1 goto end
".venv\Scripts\python.exe" -c "import sys, os, tkinter, pathlib; print('Executable:',sys.executable); print('Version:',sys.version); print('Prefix:',sys.prefix); print('Base prefix:',sys.base_prefix); print('Tk:',tkinter.TkVersion); print('PIL required: NO'); print('Bridge import: OK')"
:end
echo.
pause
