#!/usr/bin/env bash
# 由 launchd 或终端启动的 TraceMemo 草稿轮询器。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ ! -x "$REPO_DIR/.venv/bin/python" ]; then
  echo "找不到虚拟环境，请先运行 bash scripts/macos-setup.sh" >&2
  exit 1
fi

export WXAUTO_TOKEN_FILE="$REPO_DIR/.wxauto_token"
# 凭据统一从 macOS Keychain 读取，避免终端/IDE 继承旧 Token 覆盖新值。
unset DEEPSEEK_API_KEY QWEN_API_KEY DASHSCOPE_API_KEY TRACEMEMO_API_TOKEN WECHATEXPLORER_API_TOKEN WXAUTO_LLM_API_KEY WXAUTO_TOKEN

if [[ "${WXAUTO_SKIP_TRACEMEMO_BOOTSTRAP:-0}" != "1" ]]; then
  bash "$REPO_DIR/scripts/ensure-tracememo-runtime.sh"
fi

# 草稿模式和真实发送模式共用控制 App 保存的轮询设置，避免一个模式仍按旧的
# 40 秒间隔运行。缺少或异常时回到与发送模式一致的 5 秒默认值。
INTERVAL_FILE="$REPO_DIR/var/poll-interval"
if [ -s "$INTERVAL_FILE" ] && [[ "$(tr '[:upper:]' '[:lower:]' < "$INTERVAL_FILE")" =~ ^[0-9]+$ ]]; then
  POLL_INTERVAL="$(tr -d '[:space:]' < "$INTERVAL_FILE")"
else
  POLL_INTERVAL=5
fi
if [ "$POLL_INTERVAL" -lt 5 ] 2>/dev/null; then POLL_INTERVAL=5; fi
if [ "$POLL_INTERVAL" -gt 300 ] 2>/dev/null; then POLL_INTERVAL=300; fi
exec "$REPO_DIR/.venv/bin/python" macos/tracememo_poller.py --interval "$POLL_INTERVAL" "$@"
