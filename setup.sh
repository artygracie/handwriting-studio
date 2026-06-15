#!/usr/bin/env bash
# One-time setup: create a native-arm64 virtualenv and install dependencies.
#
# We deliberately avoid the system (x86_64/Rosetta) conda here: TensorFlow's
# Intel wheels need AVX, which Rosetta can't emulate, and an x86_64 conda that
# builds an arm64 env produces binaries the kernel kills on launch (code-sign
# failure). A venv off a native arm64 Python sidesteps both problems.
set -e
cd "$(dirname "$0")"

# Find a native Python in the 3.8–3.11 range (tensorflow-macos requirement).
pick_python() {
  for c in python3.11 python3.10 python3.9 /usr/bin/python3 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" - <<'PY' 2>/dev/null && { echo "$c"; return; }
import sys, platform
v = sys.version_info
ok = (3, 8) <= (v.major, v.minor) <= (3, 11)
# On Apple Silicon, require a native arm64 interpreter.
arm = platform.machine() == "arm64"
sys.exit(0 if (ok and (arm or platform.system() != "Darwin")) else 1)
PY
  done
  echo ""
}

PY="$(pick_python)"
if [ -z "$PY" ]; then
  echo "ERROR: need a native Python 3.8–3.11 (e.g. /usr/bin/python3). None found." >&2
  exit 1
fi
echo "Using interpreter: $PY ($("$PY" -c 'import platform;print(platform.python_version(), platform.machine())'))"

echo "Creating virtualenv at ./venv …"
"$PY" -m venv venv

echo "Installing dependencies (TensorFlow is a large download, please wait)…"
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

echo
echo "Done. Start the studio with:  ./run.sh"
