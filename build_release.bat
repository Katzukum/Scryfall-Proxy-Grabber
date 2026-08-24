@echo off
setlocal

REM Run from this script's directory so paths are stable.
cd /d "%~dp0"

set "APP_NAME=ProxyToolBox"
set /p "APP_VERSION=Enter release version (example: 2.1.0): "

if "%APP_VERSION%"=="" (
  echo [ERROR] Version is required.
  pause
  exit /b 1
)

set "RELEASE_EXE=%APP_NAME%-v%APP_VERSION%.exe"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
  echo Create it first, then run this builder again.
  pause
  exit /b 1
)

if not exist "frontend\package.json" (
  echo [ERROR] Frontend folder not found at .\frontend
  pause
  exit /b 1
)

echo APP_VERSION = "%APP_VERSION%" > "src\app_version.py"
echo export const APP_VERSION = "%APP_VERSION%" ^; > "frontend\src\version.ts"

echo [INFO] Building frontend for version %APP_VERSION%...
call ".venv\Scripts\activate.bat"
cd /d ".\frontend"
call npm run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  pause
  exit /b 1
)
cd /d "%~dp0"

call ".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo [INFO] PyInstaller not found. Installing it into the virtual environment...
  call ".venv\Scripts\python.exe" -m pip install pyinstaller
  if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
  )
)

if exist "release\%RELEASE_EXE%" del /q "release\%RELEASE_EXE%"

call ".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --distpath "release" ^
  --workpath "build\pyinstaller" ^
  "proxytoolbox.spec"

if errorlevel 1 (
  echo [ERROR] EXE build failed.
  pause
  exit /b 1
)

echo.
if not exist "release\%APP_NAME%.exe" (
  echo [ERROR] Built EXE not found at %cd%\release\%APP_NAME%.exe
  pause
  exit /b 1
)

move /y "release\%APP_NAME%.exe" "release\%RELEASE_EXE%" >nul
if errorlevel 1 (
  echo [ERROR] Failed to rename built EXE.
  pause
  exit /b 1
)

echo [OK] Build complete: %cd%\release\%RELEASE_EXE%
echo Share that file with your friend.

endlocal
