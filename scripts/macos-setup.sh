#!/usr/bin/env bash
#
# Mac 常开方案的一键配置。
#
# 装完之后：规则服务由 launchd 托管、开机自启、崩了自动拉起；
# 采集端需要手动跑（它要辅助功能权限，launchd 拉起的进程权限归属容易出问题）。
#
# 用法：
#   bash scripts/macos-setup.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

PLIST_LABEL="com.wxauto.server"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
VENV="$REPO_DIR/.venv"

echo "==> 检查 Python"
# 不用 command -v python3：macOS 自带的 /usr/bin/python3 是个占位符，
# 存在但不可用，执行它会弹窗要求安装 Xcode 命令行工具（国内常下载失败，
# 且每次调用都会重新弹）。只认真正可用的解释器。
PY=""
for candidate in \
    /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3
do
    [ -x "$candidate" ] && PY="$candidate" && break
done
if [ -z "$PY" ] && xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ]; then
    PY="/usr/bin/python3"
fi
if [ -z "$PY" ]; then
    echo "找不到可用的 python3。" >&2
    echo "从 https://www.python.org/downloads/macos/ 装一个即可" >&2
    echo "（弹出「安装命令行开发者工具」时选「以后」，本项目不需要它）" >&2
    exit 1
fi
"$PY" --version

echo
echo "==> 建虚拟环境（避免污染系统 Python）"
if [ ! -d "$VENV" ]; then
    "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet fastapi "uvicorn[standard]" pyyaml requests
echo "依赖装好了"

echo
echo "==> 生成配置"
if [ -f core/config.yaml ]; then
    echo "core/config.yaml 已存在，跳过（重新答一遍：$VENV/bin/python -m core.wizard）"
elif [ -t 0 ]; then
    # 有终端就走问答，把整套回复内容按你的答案生成出来。
    # 直接抄示例配置的话，所有人的自动回复长得一模一样。
    "$VENV/bin/python" -m core.wizard || {
        echo "跳过问答，先放一份示例配置"
        cp core/config.example.yaml core/config.yaml
    }
else
    cp core/config.example.yaml core/config.yaml
    echo "非交互环境，先放一份示例配置（之后跑 $VENV/bin/python -m core.wizard 生成你自己的）"
fi

TOKEN_FILE="$REPO_DIR/.wxauto_token"
if [ ! -f "$TOKEN_FILE" ]; then
    "$PY" -c "import secrets; print(secrets.token_hex(16))" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
fi
TOKEN="$(cat "$TOKEN_FILE")"

mkdir -p "$REPO_DIR/var"

echo
echo "==> 写 launchd 配置（规则服务开机自启）"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV}/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>server.app:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8848</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>WXAUTO_CONFIG</key>
        <string>core/config.yaml</string>
        <key>WXAUTO_STATE</key>
        <string>var/state.json</string>
        <key>WXAUTO_TOKEN</key>
        <string>${TOKEN}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${REPO_DIR}/var/server.log</string>
    <key>StandardErrorPath</key>
    <string>${REPO_DIR}/var/server.err.log</string>
</dict>
</plist>
EOF

# 只监听 127.0.0.1：服务和采集端都在这台 Mac 上，没必要暴露到局域网。
# 你朋友的安卓跑的是他自己那套（见 scripts/termux-setup.sh），不连你这台。

echo "==> 加载服务"
launchctl bootout "gui/$(id -u)/${PLIST_LABEL}" 2>/dev/null || true
# 这个标记在重启或手动停止后仍可能保留；不先启用，下面的 bootstrap 会直接失败。
launchctl enable "gui/$(id -u)/${PLIST_LABEL}"
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
sleep 2

echo
echo "==> 写采集端启动脚本"
cat > "$REPO_DIR/run-mac-bot.sh" <<EOF
#!/usr/bin/env bash
set -e
cd "$REPO_DIR"

export WXAUTO_SERVER=http://127.0.0.1:8848
export WXAUTO_TOKEN="$TOKEN"

# 想让 iPhone 也参与时（同一个微信号），两端填相同的 account：
# export WXAUTO_ACCOUNT=我

# caffeinate 防止 Mac 睡眠导致采集中断；关掉这个脚本它也会跟着退出。
exec caffeinate -i "$VENV/bin/python" macos/wechat_mac_bot.py "\$@"
EOF
chmod +x "$REPO_DIR/run-mac-bot.sh"

echo
echo "==> 自检"
if curl -sf --max-time 5 http://127.0.0.1:8848/health >/dev/null 2>&1; then
    echo "规则服务已就绪：$(curl -s http://127.0.0.1:8848/health)"
else
    echo "服务还没起来，看一下日志：tail -f var/server.err.log" >&2
fi

echo
echo "============================================================"
echo "规则服务装好了，已设为开机自启。"
echo
echo "接下来还有两步："
echo
echo "  1) 授权辅助功能"
echo "     系统设置 → 隐私与安全性 → 辅助功能 → 勾选「终端」"
echo "     （不给这个权限，采集端读不到微信窗口）"
echo
echo "  2) 先干跑，确认规则符合预期再真发"
echo "     ./run-mac-bot.sh --dry-run"
echo "     ./run-mac-bot.sh"
echo
echo "常用操作："
echo "  改规则      vim core/config.yaml"
echo "  规则热重载  curl -X POST -H \"Authorization: Bearer \$(cat .wxauto_token)\" \\"
echo "                   http://127.0.0.1:8848/reload"
echo "  看服务日志  tail -f var/server.log"
echo "  停止服务    launchctl unload $PLIST_PATH"
echo
echo "另外：系统设置 → 电池 → 选「永不」进入睡眠，否则合盖就停了。"
echo "============================================================"
