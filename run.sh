#!/usr/bin/env bash
# Launch the Inkwell studio at http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
if [ ! -x venv/bin/python ]; then
  echo "No venv found — run ./setup.sh first." >&2
  exit 1
fi
echo "Starting Inkwell at http://127.0.0.1:8000  (Ctrl+C to stop)"
exec venv/bin/python server.py
