#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO_DIR/dist/TraceMemo 自动回复.app"

if [[ ! -d "$APP" ]]; then
  bash "$REPO_DIR/scripts/build-macos-app.sh"
fi
open "$APP"
