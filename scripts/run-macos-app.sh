#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO_DIR/dist/TraceMemo 自动回复.app"

# Pull a fast-forward main update when safe, then rebuild only when the
# generated bundle does not match the checked-out source revision.
bash "$REPO_DIR/scripts/update-macos-app.sh"
open "$APP"
