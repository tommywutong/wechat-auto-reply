#!/bin/bash
#
# 双击这个文件就能装。不用会用终端。
#
# （Finder 里双击 .command 文件会自动打开「终端」并运行它，
#  所以使用者只需要双击，不需要自己敲任何命令。）

cd "$(dirname "$0")" || exit 1

# 出错时不要一闪而过关掉窗口，让人能看见错误信息
trap 'echo; echo "出错了。把上面红色的内容截图发给帮你配置的人。"; echo; read -n 1 -s -r -p "按任意键关闭..."' ERR

set -e

clear
cat <<'BANNER'
============================================================
             微信自动回复 —— Mac 安装程序
============================================================

这个程序会：
  1. 检查并准备运行环境
  2. 生成你的配置文件和密码
  3. 把「自动回复服务」设成开机自动启动

整个过程 2-5 分钟，中途可能需要你输入 Mac 的开机密码。

BANNER

read -n 1 -s -r -p "准备好了就按任意键开始（想退出就直接关窗口）..."
echo
echo

# ---------------------------------------------------------- 环境检查

echo "【1/5】检查运行环境"

# 找一个「真的」Python。
#
# 这里不能用 command -v python3：macOS 自带的 /usr/bin/python3 是个占位符，
# 文件存在但不是 Python——一执行它，系统就会弹窗让你装 Xcode 命令行工具。
# 那个下载在国内经常失败，而且脚本每调用一次 python3 就弹一次，
# 关掉还会再弹，非常烦人。所以：只在确认装了开发者工具的前提下才碰它。
PY=""
for candidate in \
    /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3
do
    if [ -x "$candidate" ]; then PY="$candidate"; break; fi
done

# 只有装了命令行工具，/usr/bin/python3 才是真的能用的
if [ -z "$PY" ] && xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ]; then
    PY="/usr/bin/python3"
fi

if [ -z "$PY" ]; then
    echo
    echo "  ┌────────────────────────────────────────────────────────┐"
    echo "  │  还缺一个 Python，装一下就好（大约 3 分钟）             │"
    echo "  └────────────────────────────────────────────────────────┘"
    echo
    echo "  ⚠️ 重要：如果屏幕上弹出「需要安装命令行开发者工具」，"
    echo "     请点「以后」或「取消」，不要点安装。"
    echo "     那个东西又大又容易下载失败，我们不需要它。"
    echo
    echo "  正在打开 Python 官网下载页面。请找到："
    echo
    echo "       macOS 64-bit universal2 installer"
    echo
    echo "  下载到的是一个 .pkg 文件，双击它，一路点「继续」装完。"
    echo "  装完之后回来重新双击「安装到Mac.command」就行。"
    echo
    open "https://www.python.org/downloads/macos/"
    read -n 1 -s -r -p "按任意键关闭本窗口..."
    exit 0
fi

echo "      Python 有了 ($("$PY" --version 2>&1))"

if [ ! -d "/Applications/WeChat.app" ]; then
    echo
    echo "  ⚠️  没找到 Mac 版微信。"
    echo "      请先去 App Store 装「微信」并登录，再回来双击本文件。"
    echo
    read -n 1 -s -r -p "按任意键关闭..."
    exit 0
fi
echo "      微信有了"

# ---------------------------------------------------------- 依赖

echo
echo "【2/5】准备运行环境（第一次会慢一点，请耐心等）"
VENV=".venv"
[ -d "$VENV" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet fastapi "uvicorn[standard]" pyyaml requests
echo "      好了"

# ---------------------------------------------------------- 配置

echo
echo "【3/5】生成你的回复内容"
if [ -f core/config.yaml ]; then
    echo "      配置文件已存在，保留你之前改过的内容"
    echo "      想重新答一遍：$VENV/bin/python -m core.wizard"
else
    # 问几个问题把整套话生成出来。直接抄一份示例配置，
    # 结果就是所有人的自动回复长得一模一样——那还不如不回。
    if ! "$VENV/bin/python" -m core.wizard; then
        echo
        echo "      跳过了问答，先放一份示例配置"
        cp core/config.example.yaml core/config.yaml
        echo "      想以后再答：$VENV/bin/python -m core.wizard"
    fi
fi

if [ ! -f .wxauto_token ]; then
    "$PY" -c "import secrets; print(secrets.token_hex(16))" > .wxauto_token
    chmod 600 .wxauto_token
fi
TOKEN="$(cat .wxauto_token)"
mkdir -p var

# ---------------------------------------------------------- 后台服务

echo
echo "【4/5】设置开机自动启动"
REPO_DIR="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.wxauto.server.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.wxauto.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>${REPO_DIR}/.venv/bin/python</string>
        <string>-m</string><string>uvicorn</string>
        <string>server.app:app</string>
        <string>--host</string><string>127.0.0.1</string>
        <string>--port</string><string>8848</string>
    </array>
    <key>WorkingDirectory</key><string>${REPO_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>WXAUTO_CONFIG</key><string>core/config.yaml</string>
        <key>WXAUTO_STATE</key><string>var/state.json</string>
        <key>WXAUTO_TOKEN</key><string>${TOKEN}</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>${REPO_DIR}/var/server.log</string>
    <key>StandardErrorPath</key><string>${REPO_DIR}/var/server.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 3

if curl -sf --max-time 5 http://127.0.0.1:8848/health >/dev/null 2>&1; then
    echo "      服务已启动"
else
    echo "      ⚠️ 服务没起来，稍后可以把 var/server.err.log 发给帮你配置的人"
fi

# ---------------------------------------------------------- 启动器

echo
echo "【5/5】生成桌面快捷方式"

# 文件名带序号：不写清楚先点哪个，多数人会直接点最后那个
cat > "1 检查微信.command" <<EOF
#!/bin/bash
cd "\$(dirname "\$0")"
clear
echo "=========================================================="
echo "  检查程序能不能正常读到微信的界面"
echo "  这一步只看不动：不读消息，也不发消息"
echo "=========================================================="
echo
"$REPO_DIR/.venv/bin/python" macos/wechat_mac_bot.py --doctor
echo
echo "=========================================================="
echo "  看最后那几行：出现 ✅ 就可以双击「2 试运行」了。"
echo "  出现 ❌ 就把这个窗口整个截图发给帮你配置的人。"
echo "=========================================================="
echo
read -n 1 -s -r -p "按任意键关闭..."
EOF

# 更新程序。
#
# 没有这个的话，我这边改了代码，用户这边是拿不到的——他不会用 git，
# 而 /usr/bin/git 在没装开发者工具的机器上又是个会弹窗的占位符。
# 所以走 curl + unzip：这两个是 macOS 自带的真程序，不弹任何东西。
#
# 只覆盖代码，绝不碰 core/config.yaml（你答的那套回复内容）
# 和 .wxauto_token（密码），那两个丢了要重来一遍。
cat > "0 更新程序.command" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")" || exit 1
clear
echo "=========================================================="
echo "  更新到最新版本"
echo "  你答过的问题和生成的回复内容不会丢"
echo "=========================================================="
echo

ZIP_URL="https://github.com/tommywutong/wechat-auto-reply/archive/refs/heads/main.zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "  正在下载..."
if ! curl -fsSL --max-time 120 -o "$TMP/main.zip" "$ZIP_URL"; then
    echo
    echo "  ❌ 下载失败。多半是网络问题，过一会儿再试一次。"
    echo
    read -n 1 -s -r -p "按任意键关闭..."
    exit 1
fi

if ! unzip -q -o "$TMP/main.zip" -d "$TMP"; then
    echo "  ❌ 解压失败。"
    read -n 1 -s -r -p "按任意键关闭..."
    exit 1
fi

SRC="$(find "$TMP" -maxdepth 1 -type d -name 'wechat-auto-reply-*' | head -1)"
if [ -z "$SRC" ] || [ ! -d "$SRC/core" ]; then
    echo "  ❌ 下载到的内容不对，没动你的文件。"
    read -n 1 -s -r -p "按任意键关闭..."
    exit 1
fi

# 先把要保住的东西挪到一边
SAVE="$TMP/save"
mkdir -p "$SAVE"
[ -f core/config.yaml ] && cp core/config.yaml "$SAVE/config.yaml"

echo "  正在更新代码..."
for d in core macos server; do
    [ -d "$SRC/$d" ] && mkdir -p "$d" && cp -R "$SRC/$d/." "$d/"
done
[ -f "$SRC/安装到Mac.command" ] && cp "$SRC/安装到Mac.command" . && chmod +x "安装到Mac.command"

# 放回去。config.yaml 是你答问题生成的，压缩包里那份是示例，不能盖掉
[ -f "$SAVE/config.yaml" ] && cp "$SAVE/config.yaml" core/config.yaml

# 后台服务在跑旧代码，重启一下
PLIST="$HOME/Library/LaunchAgents/com.wxauto.server.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null
    launchctl load "$PLIST" 2>/dev/null
fi

echo
echo "  ✅ 更新好了。现在可以双击「1 检查微信」。"
echo
read -n 1 -s -r -p "按任意键关闭..."
EOF

cat > "查看联系人名字.command" <<EOF
#!/bin/bash
cd "\$(dirname "\$0")"
clear
echo "=========================================================="
echo "  列出程序看到的会话名"
echo "  白名单（只对这几个人自动回复）就填这里的名字，照抄即可"
echo "  这一步只看不动：不读消息，也不发消息"
echo "=========================================================="
"$REPO_DIR/.venv/bin/python" macos/wechat_mac_bot.py --contacts
echo
read -n 1 -s -r -p "按任意键关闭..."
EOF

cat > "2 试运行（不真发消息）.command" <<EOF
#!/bin/bash
cd "\$(dirname "\$0")"
export WXAUTO_SERVER=http://127.0.0.1:8848
export WXAUTO_TOKEN="$TOKEN"
clear
echo "=========================================================="
echo "  试运行模式：只显示「本来会回什么」，不会真的发出去"
echo
echo "  注意：读消息需要点开会话，所以未读会被标成已读。"
echo "  确认没问题后，再用「3 开始自动回复」那个文件"
echo "  想停止：按 Control + C，或直接关掉这个窗口"
echo "=========================================================="
echo
exec caffeinate -i "$REPO_DIR/.venv/bin/python" macos/wechat_mac_bot.py --dry-run
EOF

cat > "3 开始自动回复.command" <<EOF
#!/bin/bash
cd "\$(dirname "\$0")"
export WXAUTO_SERVER=http://127.0.0.1:8848
export WXAUTO_TOKEN="$TOKEN"
clear
echo "=========================================================="
echo "  自动回复运行中，会真的发消息了。"
echo "  这个窗口关掉就停了。"
echo "  想停止：按 Control + C，或直接关掉这个窗口"
echo "=========================================================="
echo
exec caffeinate -i "$REPO_DIR/.venv/bin/python" macos/wechat_mac_bot.py
EOF

chmod +x "0 更新程序.command" "1 检查微信.command" \
        "2 试运行（不真发消息）.command" "3 开始自动回复.command" \
        "查看联系人名字.command"
echo "      好了"

# ---------------------------------------------------------- 授权引导

echo
echo "============================================================"
echo "  安装完成！但还差最后一步授权，不做的话读不到微信消息"
echo "============================================================"
echo
echo "  现在会自动打开「辅助功能」设置页面。请在里面："
echo
echo "     找到「终端」并把开关打开"
echo "     （如果列表里没有「终端」，点下面的 ➕ 号，"
echo "       从「应用程序 → 实用工具」里选「终端」）"
echo
read -n 1 -s -r -p "按任意键打开设置页面..."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
echo
echo
echo "------------------------------------------------------------"
# 把文件夹在访达里打开。
# 用户装完之后最常卡的一步就是「那几个文件在哪」——
# 让他自己去翻文件夹是没必要的摩擦，直接摆到他面前。
open .

echo "  已经帮你打开文件夹了。授权完成后，回到那个窗口，"
echo "  在文件列表**最上面**按数字顺序双击这三个文件："
echo
echo "     「1 检查微信.command」"
echo "        看程序能不能读到微信界面。只看不动，很安全。"
echo "        全是 [OK] 就继续；出现 [X ] 就截图求助。"
echo
echo "     「2 试运行（不真发消息）.command」"
echo "        看它会回什么，但不会真的发出去。"
echo
echo "     「3 开始自动回复.command」"
echo "        确认前两步都没问题后再用这个，它会真的发消息。"
echo
echo "  另外建议：系统设置 → 电池 → 把「睡眠」设成「永不」，"
echo "           否则合上盖子自动回复就停了。"
echo "------------------------------------------------------------"
echo
read -n 1 -s -r -p "按任意键关闭..."
