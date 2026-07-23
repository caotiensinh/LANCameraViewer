@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_and_run.ps1"
if errorlevel 1 pause
