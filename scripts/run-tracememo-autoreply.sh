#!/usr/bin/env bash
# TraceMemo -> DeepSeek -> 本地微信界面自动回复。
# 真实发送只对 core/config.yaml 白名单生效；群聊必须 @ 当前昵称。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ ! -x "$REPO_DIR/.venv/bin/python" ]; then
  echo "找不到虚拟环境，请先运行 bash scripts/macos-setup.sh" >&2
  exit 1
fi

export WXAUTO_TOKEN_FILE="$REPO_DIR/.wxauto_token"
# 凭据统一从 macOS Keychain 读取，避免终端/IDE 继承旧 Token 覆盖新值。
unset DEEPSEEK_API_KEY TRACEMEMO_API_TOKEN WECHATEXPLORER_API_TOKEN WXAUTO_LLM_API_KEY WXAUTO_TOKEN

INTERVAL_FILE="$REPO_DIR/var/poll-interval"
if [ -s "$INTERVAL_FILE" ] && [[ "$(cat "$INTERVAL_FILE")" =~ ^[0-9]+$ ]]; then
  POLL_INTERVAL="$(cat "$INTERVAL_FILE")"
else
  POLL_INTERVAL=5
fi
if [ "$POLL_INTERVAL" -lt 5 ] 2>/dev/null; then POLL_INTERVAL=5; fi
if [ "$POLL_INTERVAL" -gt 300 ] 2>/dev/null; then POLL_INTERVAL=300; fi
exec "$REPO_DIR/.venv/bin/python" macos/tracememo_poller.py \
  --interval "$POLL_INTERVAL" \
  --send \
  --send-all \
  "$@"
