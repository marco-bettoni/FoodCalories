@echo off
setlocal EnableExtensions

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found.
  echo Run setup.bat first.
  exit /b 1
)

echo Starting AI Food Calorie Estimator...
".venv\Scripts\python.exe" -m streamlit run app.py
exit /b %ERRORLEVEL%
