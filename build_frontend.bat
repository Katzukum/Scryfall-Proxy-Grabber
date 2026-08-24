@echo off
setlocal

REM Run from this script's directory so paths are stable.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] Virtual environment not found at .venv\Scripts\activate.bat
  echo Create it first, then run this launcher again.
  pause
  exit /b 1
)

if not exist "frontend\package.json" (
  echo [ERROR] Frontend folder not found at .\frontend
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
cd /d ".\frontend"
npm run build

endlocal
