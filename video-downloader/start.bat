@echo off
REM Lumen launcher for Windows
cd /d "%~dp0"

if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installing / updating dependencies...
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

echo Starting Lumen...
python backend\app.py
pause
