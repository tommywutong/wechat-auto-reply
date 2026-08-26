#!/usr/bin/env bash
# 安装仅生成草稿的 TraceMemo 轮询器为登录后自启动服务。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.wxauto.tracememo-poller"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"

mkdir -p "$REPO_DIR/var" "$HOME/Library/LaunchAgents"
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
    <string>${REPO_DIR}/scripts/run-tracememo-poller.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${REPO_DIR}/var/tracememo-poller.log</string>
  <key>StandardErrorPath</key>
  <string>${REPO_DIR}/var/tracememo-poller.err.log</string>
</dict>
</plist>
EOF

chmod +x "$REPO_DIR/scripts/run-tracememo-poller.sh"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
# 密钥只从 Keychain 读取，禁止把终端环境里的明文密钥继承给 launchd。
unset DEEPSEEK_API_KEY TRACEMEMO_API_TOKEN WECHATEXPLORER_API_TOKEN WXAUTO_LLM_API_KEY WXAUTO_TOKEN
for secret_var in DEEPSEEK_API_KEY TRACEMEMO_API_TOKEN WECHATEXPLORER_API_TOKEN WXAUTO_LLM_API_KEY WXAUTO_TOKEN; do
  launchctl unsetenv "$secret_var" 2>/dev/null || true
done
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "轮询器已安装：${LABEL}（仅草稿，不会发送微信消息）"
