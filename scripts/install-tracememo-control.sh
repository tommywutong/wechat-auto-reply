#!/usr/bin/env bash
# 安装给 iPhone 控制端使用的局域网控制服务。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.wxauto.tracememo-control"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
TOKEN_PATH="$REPO_DIR/var/control-token"
PAIRING_PATH="$REPO_DIR/var/control-pairing-code"
PORT="${WXAUTO_CONTROL_PORT:-8850}"

mkdir -p "$REPO_DIR/var" "$HOME/Library/LaunchAgents"
if [[ ! -s "$TOKEN_PATH" ]]; then
  "$REPO_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TOKEN_PATH"
  chmod 600 "$TOKEN_PATH"
fi
TOKEN="$(tr -d '[:space:]' < "$TOKEN_PATH")"
CODE="$("$REPO_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(8))')"
"$REPO_DIR/.venv/bin/python" - "$PAIRING_PATH" "$CODE" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
path.write_text(json.dumps({"code": sys.argv[2], "created_at": time.time()}), encoding="utf-8")
os.chmod(path, 0o600)
PY

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${REPO_DIR}/.venv/bin/python</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>server.control:APP</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>${PORT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>WXAUTO_REPO_DIR</key>
    <string>${REPO_DIR}</string>
    <key>WXAUTO_CONTROL_TOKEN</key>
    <string>${TOKEN}</string>
    <key>WXAUTO_CONTROL_PAIRING_FILE</key>
    <string>${PAIRING_PATH}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${REPO_DIR}/var/tracememo-control.log</string>
  <key>StandardErrorPath</key>
  <string>${REPO_DIR}/var/tracememo-control.err.log</string>
</dict>
</plist>
EOF

chmod +x "$REPO_DIR/scripts/install-tracememo-control.sh"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "iPhone 控制服务已启动，端口 ${PORT}。"
echo "本次配对码（10 分钟内有效）：${CODE}"
LOCAL_HOST="$(scutil --get LocalHostName 2>/dev/null || true)"
if [[ -n "$LOCAL_HOST" ]]; then
  echo "iPhone 填入的 Mac 地址：${LOCAL_HOST}.local"
else
  echo "未能读取 Mac 本地名称，请在系统设置 → 通用 → 共享中设置本地名称后重试。"
fi
