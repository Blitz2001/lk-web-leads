@echo off
REM Double-click to start Lead Agent on Windows. First run installs everything (needs Python 3.10+ from python.org).
cd /d "%~dp0"
if not exist .venv (
  echo Setting up for the first time...
  py -3 -m venv .venv || python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install -q --upgrade pip
  python -m pip install -q requests beautifulsoup4
) else (
  call .venv\Scripts\activate.bat
)
python -m leadagent
pause
