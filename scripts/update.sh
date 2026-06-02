#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SVC=pinsheet

sudo systemctl stop "$SVC"
cd "$DIR"
git pull

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
        pip install -r "$plugin/requirements.txt" --quiet
    fi
done

sudo systemctl start "$SVC"
sudo systemctl status "$SVC" --no-pager
