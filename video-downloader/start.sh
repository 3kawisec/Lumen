#!/usr/bin/env bash
# Lumen launcher for macOS / Linux
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing / updating dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "Starting Lumen..."
python backend/app.py
