@echo off
cd /d C:\\skhy-premium-monitor
set POLL_SECONDS=300
set PORT=8080
"C:\\Program Files\\Python312\\python.exe" server.py >> server.log 2>&1
