#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO_DIR/dist/TraceMemo 自动回复.app"

# The bundle is a generated, ignored artifact. Always rebuild it so opening
# this launcher cannot silently keep running an older control-panel binary.
bash "$REPO_DIR/scripts/build-macos-app.sh"
open "$APP"
