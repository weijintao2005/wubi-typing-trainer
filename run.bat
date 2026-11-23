@echo off
setlocal
cd /d "%~dp0"

set "PY=C:\ProgramData\Anaconda3\python.exe"
if exist "%PY%" goto run
where python >nul 2>nul
if errorlevel 1 goto nopy
set "PY=python"

:run
echo Starting Wubi Trainer ...
"%PY%" app.py %*
if errorlevel 1 pause
exit /b 0

:nopy
echo Python 3.9+ not found. Install Python or edit PY in this file.
pause
exit /b 1
