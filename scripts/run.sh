#!/usr/bin/env bash
# Start the local dashboard from a fresh clone with one command.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)'; then
  echo "Python 3.13 is required. Install it, then run PYTHON_BIN=/path/to/python3.13 ./run.sh" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 18+ and npm are required to build the dashboard." >&2
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet .

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add a model API key in the dashboard before your first request."
fi

if [[ ! -d dashboard/node_modules ]]; then
  npm ci --prefix dashboard
fi
npm run build --prefix dashboard

echo "Starting CodeStart at http://127.0.0.1:8000"
exec .venv/bin/codestart --dashboard
