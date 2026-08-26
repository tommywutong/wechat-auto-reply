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
unset DEEPSEEK_API_KEY TRACEMEMO_API_TOKEN WECHATEXPLORER_API_TOKEN WXAUTO_LLM_API_KEY WXAUTO_TOKEN
exec "$REPO_DIR/.venv/bin/python" macos/tracememo_poller.py --interval 40 "$@"
