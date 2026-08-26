#!/usr/bin/env bash
# 只观察已经由 launchd 运行的自动回复服务，不会启动第二个轮询器。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! launchctl print "gui/$(id -u)/com.wxauto.tracememo-autoreply" >/dev/null 2>&1; then
  echo "自动回复服务尚未安装或未运行。" >&2
  exit 1
fi

echo "正在显示自动回复状态；按 Ctrl+C 退出观察，不会停止后台服务。"
exec tail -n 0 -F "$REPO_DIR/var/tracememo-autoreply.err.log"
