@echo off
setlocal

REM Run from this script's directory so paths are stable.
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo [ERROR] Virtual environment not found at .venv\Scripts\pythonw.exe
  echo Create it first, then run this launcher again.
  pause
  exit /b 1
)

".venv\Scripts\pythonw.exe" main.py

endlocal
