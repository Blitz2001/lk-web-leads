#!/usr/bin/env bash
# Start Lead Agent on Mac/Linux:  ./start.sh   (first run installs everything; needs Python 3.10+)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Setting up for the first time..."
  python3 -m venv .venv
  . .venv/bin/activate
  python -m pip install -q --upgrade pip
  python -m pip install -q requests beautifulsoup4
else
  . .venv/bin/activate
fi
python -m leadagent "$@"
