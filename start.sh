#!/usr/bin/env bash
# CodeQuest one-click start for macOS and Linux.
# First run: creates a virtual environment, installs packages and loads demo data (a few minutes).
# Later runs: starts straight away. Stop the app with Ctrl+C.
set -e
cd "$(dirname "$0")"
URL="http://localhost:5000"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "==> Creating virtual environment (first run only)"
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"

if [ ! -f ".venv/.installed" ] || [ requirements.txt -nt ".venv/.installed" ]; then
  echo "==> Installing packages (first run takes a few minutes)"
  "$VPY" -m pip install --upgrade pip -q
  "$VPY" -m pip install -r requirements.txt -q
  touch .venv/.installed
fi

if [ ! -f "learnopt.db" ]; then
  echo "==> Loading questions, coding problems and demo students (first run only)"
  "$VPY" manage.py demo
fi

echo ""
echo "  CodeQuest is starting at $URL"
echo "  Demo logins (password demo123): student@demo.local  |  instructor@demo.local"
echo "  Sign-up codes appear in this window. Press Ctrl+C to stop."
echo ""

( sleep 3
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1
  fi ) &

exec "$VPY" run.py
