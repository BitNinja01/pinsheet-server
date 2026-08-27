#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SVC=pinsheet

sudo systemctl stop "$SVC"
cd "$DIR"
git pull

# The service runs from .venv (pinsheet.service ExecStart) — bare `pip`
# would install into the wrong interpreter. Fall back to system pip if
# no venv exists.
if [ -x "$DIR/.venv/bin/pip" ]; then
    PIP="$DIR/.venv/bin/pip"
else
    PIP=pip
fi

# Install core dependencies (new deps land here, e.g. flask-talisman #105)
"$PIP" install -r requirements.txt

# Update plugin sub-repos
for plugin in "$DIR"/plugins/*/; do
    name="$(basename "$plugin")"
    echo "=== Plugin: $name ==="

    if [ -d "$plugin/.git" ]; then
        echo "  git pull ..."
        git -C "$plugin" pull
    fi

    if [ -f "$plugin/requirements.txt" ]; then
        echo "  pip install -r requirements.txt ..."
        "$PIP" install -r "$plugin/requirements.txt" --quiet
    fi
done

sudo systemctl start "$SVC"
sudo systemctl status "$SVC" --no-pager
