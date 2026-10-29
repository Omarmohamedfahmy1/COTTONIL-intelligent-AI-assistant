@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (echo Install Python 3.12 with the Python launcher. & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 (echo Dependency installation failed. See README troubleshooting. & exit /b 1)
if not exist "data\cottonil.db" (
    if "%~1"=="" (echo Usage: START_WINDOWS.bat "C:\path\to\COTTONIL_Data.zip" & exit /b 1)
    ".venv\Scripts\python.exe" scripts\build_db.py --zip "%~1"
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" scripts\prepare_phase1_db.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" scripts\validate_db.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m streamlit run app.py
