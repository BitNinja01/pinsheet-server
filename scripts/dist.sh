#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

VERSION="${1:-1.0.0}"
DIST_DIR="$PROJECT_DIR/dist"
ZIP_NAME="pinsheet_${VERSION}.zip"

mkdir -p "$DIST_DIR"

cd "$PROJECT_DIR"

git archive --format=zip --prefix="pinsheet/" -o "$DIST_DIR/$ZIP_NAME" HEAD

echo "Distribution built: dist/$ZIP_NAME"
