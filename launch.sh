#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==================================================="
echo "  Starting EasiApply Job Automation Dashboard...   "
echo "==================================================="
echo ""
echo "[INFO] Working directory: $DIR"

# Select Python binary
PY="python3"
if ! command -v python3 &>/dev/null; then
    if command -v python &>/dev/null; then
        PY="python"
    else
        echo "[ERROR] Python 3 is required but was not found in PATH."
        exit 1
    fi
fi

echo "[INFO] Using: $($PY --version)"

# Initialize .env if missing
if [ ! -f "$DIR/.env" ]; then
    if [ -f "$DIR/.env.example" ]; then
        echo "[INFO] Initializing .env from .env.example..."
        cp "$DIR/.env.example" "$DIR/.env"
    fi
fi

# Preflight: check dependencies
echo "[INFO] Checking dependencies and app import..."
if ! $PY -c "import fastapi, uvicorn; from src.api.server import app; print('OK: app imported')" &>/dev/null; then
    echo "[INFO] Installing requirements from requirements.txt..."
    $PY -m pip install -r requirements.txt
fi

# Preflight: check Playwright Chromium binary
echo "[INFO] Checking Playwright browser binaries..."
if ! $PY -c "import sys; from pathlib import Path; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); ok = Path(p.chromium.executable_path).exists(); p.stop(); sys.exit(0 if ok else 1)" &>/dev/null; then
    echo "[INFO] Playwright Chromium not found. Installing browser binaries (one-time setup)..."
    $PY -m playwright install chromium
fi

echo "[INFO] Launching EasiApply Dashboard..."
echo "[INFO] Server starting on http://127.0.0.1:8000"
echo ""

# Open browser if possible
if command -v xdg-open &>/dev/null; then
    (sleep 2 && xdg-open "http://127.0.0.1:8000/dashboard") &
elif command -v open &>/dev/null; then
    (sleep 2 && open "http://127.0.0.1:8000/dashboard") &
fi

exec $PY -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
