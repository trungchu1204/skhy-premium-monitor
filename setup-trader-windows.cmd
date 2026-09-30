@echo off
setlocal
title SKHY Pair Trader Setup
cd /d "%~dp0"

echo.
echo ========================================
echo   SKHY Pair Trader - Windows VPS
echo ========================================
echo.

set "PY=C:\Program Files\Python312\python.exe"

if not exist "%PY%" (
  echo [1/4] Installing Python 3.12...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\python312.exe'"
  if errorlevel 1 goto :fail
  "%TEMP%\python312.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 TargetDir="C:\Program Files\Python312"
  if errorlevel 1 goto :fail
) else (
  echo [1/4] Python already installed.
)

echo [2/4] Installing requirements...
"%PY%" -m pip install -r requirements-server.txt
if errorlevel 1 goto :fail

echo [3/4] Starting local server...
start "SKHY Monitor Server" /min cmd /c "cd /d "%~dp0" && set POLL_SECONDS=300 && set PORT=8080 && "%PY%" server.py"

echo [4/4] Opening Pair Trader...
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:8080/trade"

echo.
echo DONE.
echo Keep this VPS running. Trading page is local-only.
echo To reopen later: http://127.0.0.1:8080/trade
echo.
pause
exit /b 0

:fail
echo.
echo SETUP FAILED. Take a screenshot of this window and send it to ChatGPT.
pause
exit /b 1
