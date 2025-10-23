@echo off
setlocal ENABLEDELAYEDEXPANSION
pushd "%~dp0.."

REM Optional positional arguments:
REM   %1 - database name (default: odoo)
REM   %2 - force date in YYYY-MM-DD (default: today)

if "%~1"=="" (
    set "DB_NAME=odoo"
) else (
    set "DB_NAME=%~1"
)

if "%~2"=="" (
    for /f %%a in ('powershell -NoProfile -Command "(Get-Date).ToString(''yyyy-MM-dd'')"') do set "FORCE_DATE=%%a"
) else (
    set "FORCE_DATE=%~2"
)

echo Running manual billing for database %DB_NAME% on %FORCE_DATE%

set "PY_SCRIPT=%TEMP%\manual_billing_%RANDOM%.py"
copy /Y "%~dp0manual_billing.py" "%PY_SCRIPT%" > nul

set "FORCE_DATE=%FORCE_DATE%"
python odoo-bin shell -c odoo.conf -d %DB_NAME% --no-http < "%PY_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

del "%PY_SCRIPT%" > nul 2>&1

if not "%EXIT_CODE%"=="0" (
    echo Manual billing failed with exit code %EXIT_CODE%
    popd
    exit /B %EXIT_CODE%
)

echo Manual billing completed successfully.
popd
exit /B 0
