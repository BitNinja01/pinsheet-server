#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cp "$SCRIPT_DIR/pinsheet.service" /etc/systemd/system/pinsheet.service
echo "Installed pinsheet.service. Edit /etc/systemd/system/pinsheet.service to set SECRET_KEY."
echo "Then run: systemctl daemon-reload && systemctl enable --now pinsheet"
