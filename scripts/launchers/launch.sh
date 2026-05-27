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

if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY="dev-key-$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
    echo "Generated SECRET_KEY for development: $SECRET_KEY"
fi

python "$PROJECT_DIR/source/main.py"
