@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment does not exist. Run install_and_run.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
