@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto run
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto fail
:run
.venv\Scripts\python.exe -c "import pygame; import PIL" >nul 2>nul
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)
.venv\Scripts\python.exe run.py %*
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo Could not start. Install Python 3.10+ and check the error above.
pause
exit /b 1
