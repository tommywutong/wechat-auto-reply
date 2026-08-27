#!/usr/bin/env bash
# 检查 main 的远端更新，并在安全时重建 macOS 控制 App。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$REPO_DIR/dist/TraceMemo 自动回复.app"
REVISION_FILE="$APP/Contents/Resources/git-revision"
LOCK_DIR="$REPO_DIR/var/.macos-app-update.lock"

mkdir -p "$REPO_DIR/var"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  printf 'UPDATE_RESULT=busy\n'
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

result="unchanged"
if git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch="$(git -C "$REPO_DIR" branch --show-current 2>/dev/null || true)"
  dirty="$(git -C "$REPO_DIR" status --porcelain --untracked-files=all 2>/dev/null || true)"
  if [[ "$branch" == "main" && -z "$dirty" ]]; then
    if git -C "$REPO_DIR" fetch --quiet origin main >/dev/null 2>&1; then
      local_head="$(git -C "$REPO_DIR" rev-parse HEAD)"
      remote_head="$(git -C "$REPO_DIR" rev-parse origin/main)"
      if [[ "$local_head" != "$remote_head" ]] && \
        git -C "$REPO_DIR" merge-base --is-ancestor "$local_head" "$remote_head"; then
        git -C "$REPO_DIR" merge --ff-only --quiet origin/main
        result="updated"
      elif [[ "$local_head" != "$remote_head" ]]; then
        # Never rewrite local history from an App launch.
        result="skipped"
      fi
    else
      result="skipped"
    fi
  elif [[ -n "$dirty" ]]; then
    result="skipped"
  fi
fi

head="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')"
installed=""
if [[ -f "$REVISION_FILE" ]]; then
  installed="$(<"$REVISION_FILE")"
fi

if [[ ! -x "$APP/Contents/MacOS/TraceMemoAutoReply" || "$installed" != "$head" ]]; then
  if [[ "$result" != "skipped" || -z "${dirty:-}" ]]; then
    bash "$REPO_DIR/scripts/build-macos-app.sh"
    result="updated"
  fi
fi

printf 'UPDATE_RESULT=%s\n' "$result"
