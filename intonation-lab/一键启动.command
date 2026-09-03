#!/bin/bash
# Intonation Debug Lab — macOS double-click launcher (Terminal.app).
# Mirrors 一键启动.bat: find Python 3.10+, venv, deps, free port 8507, open browser.

cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
printf '\033]0;Intonation Debug Lab\007'

echo "=============================================="
echo "  Intonation Debug Lab  -  Pitch Curve Editor"
echo "=============================================="
echo

die() {
  echo "[ERROR] $*"
  echo
  echo "Press Return to close this window."
  read -r _
  exit 1
}

# Finder-launched .command files often have a minimal PATH (no Homebrew).
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

is_good_python() {
  local bin="$1"
  [[ -n "$bin" && -x "$bin" ]] || return 1
  "$bin" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null
}

find_base_python() {
  local p seen=""
  for p in \
    /opt/homebrew/bin/python3 \
    /opt/homebrew/bin/python3.13 \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3.10 \
    /usr/local/bin/python3 \
    /usr/local/bin/python3.13 \
    /usr/local/bin/python3.12 \
    /usr/local/bin/python3.11 \
    /usr/local/bin/python3.10 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    "$(command -v python3 2>/dev/null)" \
    "$(command -v python 2>/dev/null)" \
    /usr/bin/python3
  do
    [[ -n "$p" ]] || continue
    case " $seen " in
      *" $p "*) continue ;;
    esac
    seen="$seen $p"
    if is_good_python "$p"; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

VENV_PY=".venv/bin/python"
PY=""

if is_good_python "$VENV_PY"; then
  PY="$VENV_PY"
else
  BASE="$(find_base_python)" || true
  [[ -n "$BASE" ]] || die "Python 3.10+ not found.
Install from https://www.python.org/downloads/macos/
or: brew install python
A stale or Windows-copied .venv is ignored automatically."

  echo "[1/4] Creating .venv with: $BASE"
  if ! "$BASE" -m venv --clear .venv; then
    die "Failed to create virtual environment with:
  $BASE"
  fi
  PY="$VENV_PY"
  is_good_python "$PY" || die "Virtual environment python is not usable."
fi

echo "[1/4] Python: $PY"

if ! "$PY" -c "import streamlit, numpy, soundfile" 2>/dev/null; then
  echo "[2/4] Installing dependencies on first run, please wait..."
  if ! "$PY" -m pip --version >/dev/null 2>&1; then
    "$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
  fi
  if ! "$PY" -m pip install -r requirements.txt; then
    die "Dependency install failed. Please check your network."
  fi
fi
echo "[2/4] Dependencies OK"

echo "[3/4] Checking port 8507..."
PIDS="$(lsof -tiTCP:8507 -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$PIDS" ]]; then
  echo "Port 8507 is occupied by PID $PIDS - stopping it to start fresh..."
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null || true
  sleep 2
  PIDS="$(lsof -tiTCP:8507 -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$PIDS" ]]; then
    # shellcheck disable=SC2086
    kill -9 $PIDS 2>/dev/null || true
    sleep 1
  fi
fi

echo "[4/4] Starting server: http://localhost:8507"
if [[ "${DSH_NO_BROWSER:-}" != "1" ]]; then
  (sleep 4 && open "http://localhost:8507") &
fi

"$PY" -m streamlit run app.py \
  --server.headless=true \
  --server.address=localhost \
  --server.port=8507 \
  --browser.gatherUsageStats=false

echo
echo "Server stopped. Press Return to close this window."
read -r _
exit 0
