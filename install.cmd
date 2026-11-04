@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows.ps1" install
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
