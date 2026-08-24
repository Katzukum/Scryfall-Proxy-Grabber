@echo off
setlocal enabledelayedexpansion
cls
echo ===================================================
echo   SHAI-HULUD WORM INTEGRITY CHECK (VENV SUPPORT)
echo ===================================================
echo.

set "INFECTED_FOUND=0"
set "VENV_ACTIVE=0"

:: -----------------------------------------------------
:: PART 1: DETECT AND ACTIVATE VIRTUAL ENVIRONMENT
:: -----------------------------------------------------
echo [*] Locating local Python virtual environment...

set "VENV_PATH="
if exist "venv\Scripts\activate.bat" set "VENV_PATH=venv"
if exist ".venv\Scripts\activate.bat" set "VENV_PATH=.venv"
if exist "env\Scripts\activate.bat" set "VENV_PATH=env"

if defined VENV_PATH (
    echo [+] Found local venv folder: \%VENV_PATH%
    echo [*] Activating virtual environment...
    call "%VENV_PATH%\Scripts\activate.bat"
    set "VENV_ACTIVE=1"
) else (
    echo [!] No local venv folder found (checked venv, .venv, env^).
    echo [!] Falling back to global system python execution context...
)
echo.

:: -----------------------------------------------------
:: PART 2: PIP / PYPI DEPENDENCY CHECK
:: -----------------------------------------------------
echo [*] Inspecting Python dependencies...
where pip >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] pip is inaccessible. Skipping Python environment check.
) else (
    :: Output local freeze snapshot to temp directory
    pip list --format=freeze > "%temp%\pip_list.txt" 2>nul
    
    :: Check mistralai (Infected: 2.2.2, 2.2.3, 2.2.4)
    findstr /i /c:"mistralai==2.2.2" "%temp%\pip_list.txt" >nul && (echo [!!] DANGER: Found infected mistralai==2.2.2 & set "INFECTED_FOUND=1")
    findstr /i /c:"mistralai==2.2.3" "%temp%\pip_list.txt" >nul && (echo [!!] DANGER: Found infected mistralai==2.2.3 & set "INFECTED_FOUND=1")
    findstr /i /c:"mistralai==2.2.4" "%temp%\pip_list.txt" >nul && (echo [!!] DANGER: Found infected mistralai==2.2.4 & set "INFECTED_FOUND=1")
    
    :: Check guardrails-ai (Infected: 0.10.1)
    findstr /i /c:"guardrails-ai==0.10.1" "%temp%\pip_list.txt" >nul && (echo [!!] DANGER: Found infected guardrails-ai==0.10.1 & set "INFECTED_FOUND=1")
    
    del "%temp%\pip_list.txt"
    if "!INFECTED_FOUND!"=="0" echo [+] Python venv packages appear clean.
)
echo.

:: -----------------------------------------------------
:: PART 3: CLEANUP VENV & NPM SCAN
:: -----------------------------------------------------
if "!VENV_ACTIVE!"=="1" (
    echo [*] Deactivating virtual environment...
    call deactivate
)
echo.

echo [*] Checking Node.js / npm frontend dependencies...
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] npm is not installed or not in PATH. Skipping npm check.
) else (
    if not exist "package.json" (
        echo [!] No package.json found in this root folder. Skipping npm tree check.
    ) else (
        npm ls --json > "%temp%\npm_tree.json" 2>nul
        
        findstr /r /c:"\"version\": \"1\.169\.5\"" "%temp%\npm_tree.json" >nul && (
            echo [!!] DANGER: Found infected TanStack package matching version 1.169.5
            set "INFECTED_FOUND=1"
        )
        findstr /r /c:"\"version\": \"1\.169\.8\"" "%temp%\npm_tree.json" >nul && (
            echo [!!] DANGER: Found infected TanStack package matching version 1.169.8
            set "INFECTED_FOUND=1"
        )
        
        del "%temp%\npm_tree.json"
    )
    if "!INFECTED_FOUND!"=="0" echo [+] Node.js dependencies appear clean.
)

echo.
echo ===================================================
echo                      RESULTS                      
echo ===================================================
if "!INFECTED_FOUND!"=="1" (
    echo [WARNING] Malicious packages were discovered in this workspace.
    echo Actions to take:
    echo 1. Fully delete your virtual environment folder and node_modules.
    echo 2. Purge local installer caches via 'pip cache purge' and 'npm cache clean --force'.
    echo 3. Revoke/Rotate any secret environment variables, cloud keys, or npm tokens.
) else (
    echo [SUCCESS] No known Shai-Hulud worm modules detected in this workspace.
)
echo ===================================================
echo.
pause
