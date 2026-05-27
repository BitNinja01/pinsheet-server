#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SVC=pinsheet

sudo systemctl stop "$SVC"
cd "$DIR"
git pull
sudo systemctl start "$SVC"
sudo systemctl status "$SVC" --no-pager
