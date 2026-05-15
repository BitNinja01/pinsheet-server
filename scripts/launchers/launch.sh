#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/.venv"
fi

source "$PROJECT_DIR/.venv/bin/activate"

if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install -q -r "$PROJECT_DIR/requirements.txt"
fi

python "$PROJECT_DIR/source/main.py"
