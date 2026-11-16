@echo off
rem Starts Balanza on this computer. Double-click this file.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Creating the Python environment. This only happens the first time...
    python -m venv .venv
)
echo Checking the libraries...
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt
.venv\Scripts\python.exe run.py
pause
