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

# `.build/` is intentionally ignored by Git, so a fresh checkout or a cleaned
# local build can lose the Vision OCR and mouse helpers. Rebuild them before
# starting the sender instead of waiting for the first message to fail.
HELPER_DIR="$REPO_DIR/.build"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "自动回复发送模式只能在 macOS 上运行。" >&2
  exit 1
fi
if [[ ! -x "$HELPER_DIR/vision-ocr" || ! -x "$HELPER_DIR/mouse-click" || ! -x "$HELPER_DIR/mouse-scroll" ]]; then
  echo "正在准备 macOS OCR 和界面辅助程序..."
  if ! bash "$REPO_DIR/scripts/build-macos-helpers.sh"; then
    echo "macOS OCR 辅助程序准备失败，请检查 Xcode Command Line Tools。" >&2
    exit 1
  fi
fi

export WXAUTO_TOKEN_FILE="$REPO_DIR/.wxauto_token"
# 凭据统一从 macOS Keychain 读取，避免终端/IDE 继承旧 Token 覆盖新值。
unset DEEPSEEK_API_KEY QWEN_API_KEY DASHSCOPE_API_KEY TRACEMEMO_API_TOKEN WECHATEXPLORER_API_TOKEN WXAUTO_LLM_API_KEY WXAUTO_TOKEN

INTERVAL_FILE="$REPO_DIR/var/poll-interval"
if [ -s "$INTERVAL_FILE" ] && [[ "$(cat "$INTERVAL_FILE")" =~ ^[0-9]+$ ]]; then
  POLL_INTERVAL="$(cat "$INTERVAL_FILE")"
else
  POLL_INTERVAL=5
fi
if [ "$POLL_INTERVAL" -lt 5 ] 2>/dev/null; then POLL_INTERVAL=5; fi
if [ "$POLL_INTERVAL" -gt 300 ] 2>/dev/null; then POLL_INTERVAL=300; fi
REPLAY_FILE="$REPO_DIR/var/replay-offline"
set -- --interval "$POLL_INTERVAL" --send --send-all "$@"
if [ -s "$REPLAY_FILE" ] && [[ "$(tr '[:upper:]' '[:lower:]' < "$REPLAY_FILE")" =~ ^(1|true|yes|on)$ ]]; then
  set -- --replay-offline "$@"
fi
exec "$REPO_DIR/.venv/bin/python" macos/tracememo_poller.py "$@"
