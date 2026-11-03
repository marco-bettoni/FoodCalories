@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==========================================
REM FoodCalories Windows setup
REM ==========================================

cd /d "%~dp0"

set "SKIP_MODEL=0"
if /I "%~1"=="--skip-model" set "SKIP_MODEL=1"

echo.
echo === FoodCalories setup ===
echo Project: %CD%
echo.

REM 1. Check Python
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.11 or 3.12 and re-run setup.bat
  exit /b 1
)

for /f "tokens=*" %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
echo [OK] %PYVER%

REM 2. Create virtual environment if missing
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv
    exit /b 1
  )
) else (
  echo [OK] Virtual environment already exists
)

REM 3. Install dependencies
echo Installing Python packages from requirements.txt ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed
  exit /b 1
)
echo [OK] Dependencies installed

if "%SKIP_MODEL%"=="1" (
  echo.
  echo [--skip-model] Skipping Ollama model checks.
  echo Setup finished.
  exit /b 0
)

REM 4. Check Ollama CLI
where ollama >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Ollama was not found on PATH.
  echo Install Ollama from https://ollama.com then re-run setup.bat
  exit /b 1
)

for /f "tokens=*" %%V in ('ollama --version 2^>^&1') do set "OLLAVER=%%V"
echo [OK] %OLLAVER%

REM Soft version note: qwen3-vl needs 0.12.7+
echo Note: qwen3-vl:4b-instruct requires Ollama 0.12.7 or newer.
echo If your version is older, update Ollama manually. This script will not upgrade it.

REM 5. Check Ollama service
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Ollama service is not reachable at http://localhost:11434
  echo Start the Ollama application and re-run setup.bat
  exit /b 1
)
echo [OK] Ollama service is reachable

REM 6/7. Check / pull model
set "MODEL=qwen3-vl:4b-instruct"
if defined OLLAMA_MODEL set "MODEL=%OLLAMA_MODEL%"

ollama show %MODEL% >nul 2>&1
if errorlevel 1 (
  echo Model %MODEL% not found locally. Downloading...
  ollama pull %MODEL%
  if errorlevel 1 (
    echo [ERROR] Failed to download %MODEL%
    echo Fallback suggestion: set OLLAMA_MODEL=gemma3:4b and run setup.bat again
    exit /b 1
  )
) else (
  echo [OK] Model already installed: %MODEL%
)

echo.
echo === Setup completed successfully ===
echo Run the app with: run.bat
exit /b 0
